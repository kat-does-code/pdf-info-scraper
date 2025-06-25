
from datetime import datetime
import enum
from typing import Optional


class ArtifactType(enum.Enum):
    UNSPECIFIED = "unspecified"
    REGULAR_TEXT = "text"
    IMAGE = "image"
    WHITE_TEXT = "white_text"
    FILLED_RECTANGLE = "filled_rectangle"

class ExtractedArtifact:
    def __init__(self, page_number, text, object_ref=None, description="", artifact_type: ArtifactType = ArtifactType.UNSPECIFIED):
        self.page_number : int = page_number
        self.text : str = text
        self.object_ref : Optional[any] = object_ref
        self.description : Optional[str] = description

        if artifact_type is not ArtifactType.UNSPECIFIED:
            self.artifact_type = artifact_type
        else:
            # Determine artifact type based on object_ref
            match self.object_ref:
                case None:
                    self.artifact_type = ArtifactType.REGULAR_TEXT
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
    def __init__(self, path: str, author: str = "", title: str = "", subject: str = "", keywords: str = "", producer: str = "", creator: str = "", creation_date : datetime = None, modification_date : datetime = None):
        self.path: str = path
        self.author: str = author
        self.title: str = title
        self.subject: str = subject
        self.keywords: str = keywords
        self.producer: str = producer
        self.creator: str = creator
        self.creation_date : Optional[datetime] = creation_date
        self.modification_date : Optional[datetime] = modification_date
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
            "creation_date": self.creation_date.isoformat() if self.creation_date else "",
            "modification_date": self.modification_date.isoformat() if self.modification_date else "",
            "producer": self.producer,
            "creator": self.creator,
            "findings": [finding.to_dict() for finding in self.findings]
        }