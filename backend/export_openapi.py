"""Write REST OpenAPI spec for the generated Vue REST client."""
import json
from pathlib import Path

from backend.app import app


def main():
    path = Path(__file__).resolve().parent.parent / "schema" / "openapi.rest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {path}")


if __name__ == "__main__":
    main()
