import argparse
import json
from pathlib import Path
from .api import database
from .alerts import alert
from .ingest import ingest
from .models import AlertRequest, ImportRequest


def main():
    parser = argparse.ArgumentParser(description="Run one bounded movie-track job")
    parser.add_argument("job", choices=["import", "alert"])
    parser.add_argument("config", type=Path, help="Path to request JSON; same schema as API")
    args = parser.parse_args()
    payload = json.loads(args.config.read_text())
    if args.job == "import":
        result = ingest(database(), ImportRequest.model_validate(payload))
    else:
        result = alert(database(), AlertRequest.model_validate(payload))
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
