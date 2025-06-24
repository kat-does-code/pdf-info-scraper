
import enum
from typing import Optional


class ArtifactType(enum.Enum):
    TEXT = "text"
    IMAGE = "image"

class ExtractedArtifact:
    def __init__(self, page_number, text, object_ref=None, description=""):
        self.page_number : int = page_number
        self.text : str = text
        self.object_ref : Optional[any] = object_ref
        self.description : Optional[str] = description

        match self.object_ref:
            case None:
                self.artifact_type = ArtifactType.TEXT
            case _:
                self.artifact_type = ArtifactType.IMAGE

    def __repr__(self):
        return f"ExtractedArtifact(page_number={self.page_number}, text_length={len(self.text)}, object_ref={self.object_ref}, description={self.description})"

class PossibleArtifactFinding():
    def __init__(self, page_number, text, artifact_type: ArtifactType, matched_data: str, matched_data_type: str):
        self.page_number : int = page_number
        self.text : str = text
        self.artifact_type = artifact_type
        self.matched_data = matched_data
        self.matched_data_type = matched_data_type

    @staticmethod
    def from_extracted_artifact(extracted_artifact: ExtractedArtifact, matched_data: str, matched_data_type: str) -> 'PossibleArtifactFinding':
        return PossibleArtifactFinding(
            page_number=extracted_artifact.page_number,
            text=extracted_artifact.text,
            artifact_type=extracted_artifact.artifact_type,
            matched_data=matched_data,
            matched_data_type=matched_data_type
        )
    
    def to_dict(self):
        return {
            "page_number": self.page_number,
            "text": self.text,
            "artifact_type": self.artifact_type.value,
            "matched_data": self.matched_data,
            "matched_data_type": self.matched_data_type
        }
    
class ScannedPDF:
    def __init__(self, path: str, author: str = "", title: str = "", subject: str = "", keywords: str = ""):
        self.path: str = path
        self.author: str = author
        self.title: str = title
        self.subject: str = subject
        self.keywords: str = keywords
        self.findings : list[PossibleArtifactFinding] = []

    def add_findings(self, findings: list[PossibleArtifactFinding]):
        self.findings = findings

    def to_dict(self):
        return {
            "path": self.path,
            "author": self.author,
            "title": self.title,
            "subject": self.subject,
            "keywords": self.keywords,
            "findings": [finding.to_dict() for finding in self.findings]
        }