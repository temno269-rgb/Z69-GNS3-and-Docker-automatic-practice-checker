from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional

class LabType(str, Enum):
    LAB10 = "lab10"
    LAB11 = "lab11"
    LAB12 = "lab12"
    LAB13 = "lab13"
    LAB14 = "lab14"

@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    details: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'passed': self.passed,
            'message': self.message,
            'details': self.details
        }
