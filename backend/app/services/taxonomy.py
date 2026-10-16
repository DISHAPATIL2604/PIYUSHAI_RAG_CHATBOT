"""GATE DA taxonomy: powers /subjects, input validation and deterministic subject/topic tagging."""
import json
import re
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "gate_da_taxonomy.json"


def _pattern(alias: str) -> re.Pattern:
    return re.compile(r"(?<![\w])" + re.escape(alias.lower()) + r"(?![\w])")


class Taxonomy:
    def __init__(self, data: dict):
        self.courses: list[str] = list(data.get("courses", []))
        self.subjects: list[dict] = data.get("subjects", [])
        self._subj_patterns = {s["name"]: [_pattern(a) for a in [s["name"], *s.get("aliases", [])]] for s in self.subjects}
        self._topic_patterns = {
            (s["name"], t["name"]): [_pattern(a) for a in [t["name"], *t.get("aliases", [])]]
            for s in self.subjects for t in s.get("topics", [])
        }

    @classmethod
    def load(cls, path: Path | None = None) -> "Taxonomy":
        return cls(json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8")))

    def subject_list(self, course: str | None = None) -> list[dict]:
        # Single exam in the MVP taxonomy; the argument keeps the API ready for more exams.
        return [{"name": s["name"], "topics": [t["name"] for t in s.get("topics", [])]} for s in self.subjects]

    def subject_names(self) -> list[str]:
        return [s["name"] for s in self.subjects]

    def topics_for(self, subject: str) -> list[str]:
        for s in self.subjects:
            if s["name"].lower() == subject.lower():
                return [t["name"] for t in s.get("topics", [])]
        return []

    def canonical_subject(self, name: str) -> str | None:
        return next((s for s in self.subject_names() if s.lower() == name.strip().lower()), None)

    def canonical_course(self, name: str) -> str | None:
        return next((c for c in self.courses if c.lower() == name.strip().lower()), None)

    def canonical_topic(self, topic: str, subject: str | None = None) -> str | None:
        subjects = [subject] if subject else self.subject_names()
        for sn in subjects:
            for t in self.topics_for(sn):
                if t.lower() == topic.strip().lower():
                    return t
        return None

    def tag(self, text: str) -> tuple[list[str], list[str]]:
        """Return (subjects, topics) whose names/aliases occur in text. Empty if nothing matches."""
        low = (text or "").lower()
        subjects: list[str] = []
        topics: list[str] = []
        for s in self.subjects:
            name = s["name"]
            hit = any(p.search(low) for p in self._subj_patterns[name])
            for t in s.get("topics", []):
                if any(p.search(low) for p in self._topic_patterns[(name, t["name"])]):
                    topics.append(t["name"])
                    hit = True
            if hit:
                subjects.append(name)
        return subjects, list(dict.fromkeys(topics))
