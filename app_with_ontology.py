# app_with_ontology.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from owlready2 import get_ontology, sync_reasoner
import uuid
import os
from flask import send_from_directory

app = Flask(__name__)
CORS(app)

# -----------------------------
# Load ontology (try multiple candidate filenames; use absolute file URI)
# -----------------------------
from pathlib import Path

# Try a set of filenames that may exist in this workspace.
candidate_names = [
    "Newton_2ndLaw.owl",
    "Newton_2ndLaw.rdf",
    "Newton_law.ttl",
]

found_path = None
for name in candidate_names:
    p = Path(__file__).with_name(name)
    if p.exists():
        found_path = p
        break

if found_path:
    ONTO_PATH = str(found_path.resolve())
else:
    # Fallback: try whatever is present in the current working directory
    for name in candidate_names:
        if Path(name).exists():
            ONTO_PATH = str(Path(name).resolve())
            break
    else:
        # Last resort: use first candidate (will raise a clear error below)
        ONTO_PATH = candidate_names[0]

try:
    onto = get_ontology(ONTO_PATH).load()
    print("Ontology loaded:", ONTO_PATH)
except Exception as e:
    # Attempt a robust fallback: try parsing with rdflib (if available)
    try:
        import rdflib

        g = rdflib.Graph()
        # Choose parser format heuristically by extension
        if ONTO_PATH.lower().endswith(".ttl"):
            parse_fmt = "turtle"
        else:
            parse_fmt = None

        if parse_fmt:
            g.parse(ONTO_PATH, format=parse_fmt)
        else:
            # Let rdflib guess the format for rdf/xml/rdf files
            g.parse(ONTO_PATH)

        tmp_path = Path(__file__).with_name("Newton_law_converted.owl")
        g.serialize(destination=str(tmp_path), format="xml")
        onto = get_ontology(str(tmp_path)).load()
        print("Ontology loaded via conversion:", tmp_path)
    except ModuleNotFoundError:
        onto = None
        print("Could not load ontology:", e)
        print("Conversion attempt failed: 'rdflib' is not installed. Install it with: python -m pip install rdflib")
    except Exception as e2:
        onto = None
        print("Could not load ontology:", e)
        print("Conversion attempt failed:", e2)


# -----------------------------
# Helper: units, hints, formulas
# -----------------------------

def get_unit_individual(kind: str):
    """Return the ontology unit individual for mass/force/acceleration."""
    if not onto:
        return None
    if kind.lower() == "mass":
        return onto.Kilogram
    if kind.lower() == "force":
        return onto.Newton
    if kind.lower() == "acceleration":
        return onto.MeterPerSecondSquared
    return None


def get_hint_from_ontology(error_type: str):
    """Return hint text from Hint individuals in ontology, if available."""
    if not onto:
        # Fallback messages if ontology failed to load
        if error_type == "unit":
            return "Check your units: use N for force, kg for mass, and m/s^2 for acceleration."
        if error_type == "math":
            return "Re-check your calculation – did you multiply or divide correctly?"
        return "Think about which variable is missing and how to rearrange F = m × a."

    if error_type == "unit" and hasattr(onto, "Hint_Units"):
        return onto.Hint_Units.displayText[0]
    if error_type == "formula" and hasattr(onto, "Hint_Formula"):
        return onto.Hint_Formula.displayText[0]
    if error_type == "math" and hasattr(onto, "Hint_Arithmetic"):
        return onto.Hint_Arithmetic.displayText[0]

    # generic/fallback
    return "Think about which variable is missing and how to rearrange F = m × a."


def choose_formula_for_target(target: str):
    """Return a Formula individual from ontology based on unknown quantity."""
    if not onto:
        return None
    t = target.lower()
    if t == "force" and hasattr(onto, "F_equals_m_a"):
        return onto.F_equals_m_a
    if t == "acceleration" and hasattr(onto, "a_equals_F_div_m"):
        return onto.a_equals_F_div_m
    if t == "mass" and hasattr(onto, "m_equals_F_div_a"):
        return onto.m_equals_F_div_a
    return None


# -----------------------------
# Arithmetic helpers
# -----------------------------

def compute_force(mass: float, accel: float) -> float:
    return mass * accel


def compute_accel(force: float, mass: float) -> float:
    return force / mass


def compute_mass(force: float, accel: float) -> float:
    return force / accel


def classify_error(student_value, correct_value):
    """Simple numeric error classifier (math vs correct)."""
    if student_value is None:
        return "missing"
    if correct_value is None:
        return "other"

    if correct_value == 0:
        diff = abs(student_value - correct_value)
    else:
        diff = abs(student_value - correct_value) / abs(correct_value)

    if diff <= 0.01:
        return "none"
    if diff > 0.05:
        return "math"
    return "other"


# -----------------------------
# Ontology-based problem creation
# -----------------------------

def create_problem_from_request(target, given_dict):
    """
    Create a NumericProblem + Mass/Acceleration/Force individuals in the ontology
    and attach values/units from the request.
    Returns (problem_instance, mass_ind, accel_ind, force_ind)
    """
    if not onto:
        return None, None, None, None

    with onto:
        p_name = f"Problem_{uuid.uuid4().hex}"
        p = onto.NumericProblem(p_name)

        # Attach formula used for this problem based on what is unknown
        formula = choose_formula_for_target(target)
        if formula:
            p.usesFormula.append(formula)

        # Mass
        m_ind = onto.Mass(f"Mass_{uuid.uuid4().hex}")
        unit_m = get_unit_individual("mass")
        if unit_m:
            m_ind.hasUnit.append(unit_m)

        # Acceleration
        a_ind = onto.Acceleration(f"Acceleration_{uuid.uuid4().hex}")
        unit_a = get_unit_individual("acceleration")
        if unit_a:
            a_ind.hasUnit.append(unit_a)

        # Force
        f_ind = onto.Force(f"Force_{uuid.uuid4().hex}")
        unit_f = get_unit_individual("force")
        if unit_f:
            f_ind.hasUnit.append(unit_f)

        # Attach quantities to problem
        p.hasQuantity.append(m_ind)
        p.hasQuantity.append(a_ind)
        p.hasQuantity.append(f_ind)

        # Fill known values from request
        def to_float(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        m_val = to_float(given_dict.get("mass", {}).get("value"))
        a_val = to_float(given_dict.get("acceleration", {}).get("value"))
        f_val = to_float(given_dict.get("force", {}).get("value"))

        if m_val is not None:
            # owlready2 object properties that hold values are often multi-valued
            # assign as a single-element list or use .append()
            m_ind.numericalValue = [m_val]
        if a_val is not None:
            a_ind.numericalValue = [a_val]
        if f_val is not None:
            f_ind.numericalValue = [f_val]

    return p, m_ind, a_ind, f_ind


def solve_with_ontology(target, p, mass, accel, force):
    """
    Use ontology structure + Python arithmetic to compute the missing value,
    then write the answer back into the appropriate quantity individual.
    (You could call sync_reasoner() here if you want SWRL to do it instead.)
    """
    # Extract values if present
    m_val = float(mass.numericalValue[0]) if hasattr(mass, "numericalValue") and mass.numericalValue else None
    a_val = float(accel.numericalValue[0]) if hasattr(accel, "numericalValue") and accel.numericalValue else None
    f_val = float(force.numericalValue[0]) if hasattr(force, "numericalValue") and force.numericalValue else None

    correct_value = None
    if target == "force":
        if m_val is None or a_val is None:
            raise ValueError("Mass and acceleration are required to compute force.")
        correct_value = compute_force(m_val, a_val)
        # write back as a list value
        force.numericalValue = [correct_value]

    elif target == "acceleration":
        if f_val is None or m_val is None:
            raise ValueError("Force and mass are required to compute acceleration.")
        correct_value = compute_accel(f_val, m_val)
        accel.numericalValue = [correct_value]

    elif target == "mass":
        if f_val is None or a_val is None:
            raise ValueError("Force and acceleration are required to compute mass.")
        correct_value = compute_mass(f_val, a_val)
        mass.numericalValue = [correct_value]

    else:
        raise ValueError("Invalid target")

    return correct_value


# -----------------------------
# API endpoint
# -----------------------------

@app.route("/api/solve", methods=["POST"])
def solve():
    """
    Expects JSON like:
    {
      "given": {
        "mass": {"value": 4, "unit": "kg"},
        "acceleration": {"value": 3, "unit": "m/s^2"}
      },
      "target": "force",
      "studentAnswer": {"value": 11, "unit": "N"}
    }
    """
    data = request.get_json(force=True)

    target = data.get("target", "").lower()
    given = data.get("given", {})
    student = data.get("studentAnswer", {})

    # Create ontology-based problem
    p, m_ind, a_ind, f_ind = create_problem_from_request(target, given)
    if not onto or not p:
        return jsonify({"error": "Ontology not available; cannot perform intelligent reasoning."}), 500

    # Compute correct value using ontology-backed structure
    try:
        correct_value = solve_with_ontology(target, p, m_ind, a_ind, f_ind)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except ZeroDivisionError:
        return jsonify({"error": "Division by zero – check your input values."}), 400

    # Student answer
    def to_float(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    student_value = to_float(student.get("value"))
    student_unit = student.get("unit", "")

    # Very simple unit check using requested unit vs ontology default
    error_type = "none"
    # If the student provided a unit that doesn't match the ontology's expected unit, flag as unit error
    expected_unit = get_unit_individual(target)
    if expected_unit and student_unit:
        expected_str = expected_unit.label.first() if expected_unit.label else ""
        # Very loose check: just make sure the correct symbol is in there
        if target == "force" and "N" not in student_unit:
            error_type = "unit"
        elif target == "mass" and "kg" not in student_unit:
            error_type = "unit"
        elif target == "acceleration" and "m/s" not in student_unit:
            error_type = "unit"

    if error_type == "none":
        error_type = classify_error(student_value, correct_value)

    is_correct = (error_type == "none")

    # Get hint from ontology
    hint = None
    if not is_correct:
        hint = get_hint_from_ontology("unit" if error_type == "unit" else
                                      "math" if error_type == "math" else
                                      "formula" if error_type == "formula" else
                                      "other")

    response = {
        "correct": is_correct,
        "correctValue": correct_value,
        "target": target,
        "errorType": error_type,
        "hint": hint,
    }
    return jsonify(response)


@app.route("/", methods=["GET"])
def serve_index():
    """Serve the frontend index.html from the sibling `newfrontend` folder."""
    # Build absolute path to newfrontend directory (sibling to backend)
    base_dir = os.path.dirname(__file__)
    frontend_dir = os.path.normpath(os.path.join(base_dir, "..", "newfrontend"))
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(frontend_dir, "index.html")
    return ("index.html not found in newfrontend directory.", 404)


@app.route('/frontend/<path:filename>')
def serve_frontend_file(filename):
    """Serve static files from the newfrontend folder (e.g., JS/CSS)."""
    base_dir = os.path.dirname(__file__)
    frontend_dir = os.path.normpath(os.path.join(base_dir, "..", "newfrontend"))
    file_path = os.path.join(frontend_dir, filename)
    if os.path.exists(file_path):
        return send_from_directory(frontend_dir, filename)
    return ("File not found", 404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
