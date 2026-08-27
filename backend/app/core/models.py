from typing import Any, Dict, List
from pydantic import BaseModel, Field

class PopulationConfig(BaseModel):
    preset: str = 'balanced'
    size: int = Field(default=500, ge=100, le=10000)
    neighborhoods: int = Field(default=8, ge=2, le=50)

class SimulationConfig(BaseModel):
    population: PopulationConfig = Field(default_factory=PopulationConfig)
    policy_id: str = 'water_rationing'
    policy_parameters: Dict[str, float] = Field(default_factory=dict)
    rounds: int = Field(default=20, ge=1, le=100)
    seed: int = 42

class SimulationCreate(BaseModel): config: SimulationConfig
class CompareRequest(BaseModel):
    base_config: SimulationConfig
    policies: List[SimulationConfig] = Field(min_length=1,max_length=3)
class CalibrationRequest(BaseModel):
    simulated: Dict[str,float]
    observed: Dict[str,float]
    parameters: Dict[str,float] = Field(default_factory=dict)
    learning_rate: float = Field(default=.15,gt=0,le=1)

class PolicyPlanRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    objectives: List[str] = Field(default_factory=list)
    size: int = Field(default=500, ge=100, le=10000)
    rounds: int = Field(default=20, ge=1, le=100)
    seed: int = 42
