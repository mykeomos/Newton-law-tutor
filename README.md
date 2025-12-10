**Newton's Law Tutor**

A small backend service that uses an ontology to help students solve and get hints for problems based on Newton's Second Law (F = m × a). The repository contains a minimal Flask API that loads an ontology (OWL/RDF) and exposes a JSON API used by a simple frontend in the sibling `newfrontend` folder.

**Contents**
- `app_with_ontology.py`: Backend Flask application with ontology-aware problem creation and a `/api/solve` endpoint.
- `Newton_2ndLaw.owl` / `Newton_2ndLaw.rdf`: Ontology files used by the backend (one or both may be present).
- `newfrontend/`: Sibling folder (not inside this repo) with a simple `index.html` frontend that the backend can serve.

**Features**
- Loads an ontology via `owlready2` and optionally converts RDF using `rdflib` if needed.
- Creates ontology-based `NumericProblem` individuals and associated quantities.
- Computes the missing quantity (force, mass, or acceleration) and returns correctness, hints, and the correct value.
- Serves the frontend `index.html` from the sibling `newfrontend` folder.

**Prerequisites**
- Python 3.8+
- Git (repo already pushed to `https://github.com/mykeomos/Newton-law-tutor`)

Recommended Python packages (the app uses these directly):

```
flask
flask-cors
owlready2
rdflib    # optional; used only for format conversion fallbacks
```

You can install them in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install flask flask-cors owlready2 rdflib
```

**Run (development)**

From the `newbackend` folder run:

```powershell
python app_with_ontology.py
```

The backend listens by default on `http://0.0.0.0:5000` and exposes:
- `GET /` — serves `index.html` from the sibling `newfrontend` folder (if present)
- `POST /api/solve` — expects JSON describing `given` quantities and `target` and returns correctness, `correctValue`, `errorType`, and a `hint` when available.

Example `POST /api/solve` payload:

```json
{
  "given": {
    "mass": {"value": 4, "unit": "kg"},
    "acceleration": {"value": 3, "unit": "m/s^2"}
  },
  "target": "force",
  "studentAnswer": {"value": 11, "unit": "N"}
}
```

**Notes & Troubleshooting**
- If the ontology fails to load, the app attempts to use `rdflib` to parse/convert the file. Install `rdflib` if you see conversion errors.
- The repo currently sets a repository-local Git identity. If you want the identity global, run:

```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

**Contributing**
- Improve ontology hints and labels in the OWL files to enhance hint quality.
- Add unit tests for `solve_with_ontology` and the error classification logic.

**License & Contact**
- Add your preferred license file to the repository (e.g., `MIT` or `Apache-2.0`).
- Contact: `michaelomogbeleghan@gmal.com`
