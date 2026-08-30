from typing import Any, Dict, List
from pydantic import BaseModel, Field, model_validator


POLICY_PARAMETER_BOUNDS = {
    'reduction': (0.0, 0.8),
    'restoration': (0.0, 0.6),
    'subsidy': (-0.6, 0.6),
    'cost_change': (-0.6, 0.6),
}


def _validate_policy_fields(policy_id: str | None, policy_parameters: Dict[str, float]) -> Dict[str, float]:
    if policy_id is None:
        return policy_parameters
    from app.services.policies import POLICIES

    if policy_id not in POLICIES:
        supported = ', '.join(sorted(POLICIES))
        raise ValueError(f"Unsupported policy_id '{policy_id}'. Supported policies: {supported}")

    allowed_parameters = set(POLICIES[policy_id]['parameters'])
    unsupported = sorted(set(policy_parameters) - allowed_parameters)
    if unsupported:
        allowed = ', '.join(sorted(allowed_parameters))
        raise ValueError(
            f"Unsupported parameter(s) for policy '{policy_id}': {unsupported}. "
            f"Allowed parameters: {allowed}"
        )

    for parameter_name, value in policy_parameters.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"Policy parameter '{parameter_name}' for policy '{policy_id}' must be numeric.")
        lower_bound, upper_bound = POLICY_PARAMETER_BOUNDS.get(parameter_name, (0.0, 1.0))
        numeric_value = float(value)
        if not lower_bound <= numeric_value <= upper_bound:
            raise ValueError(
                f"Policy parameter '{parameter_name}' for policy '{policy_id}' is out of range: "
                f"{numeric_value} not in [{lower_bound}, {upper_bound}]"
            )

    return policy_parameters


class PopulationConfig(BaseModel):
    preset: str = 'balanced'
    size: int = Field(default=10000, ge=10000, le=10000)
    neighborhoods: int = Field(default=8, ge=2, le=50)


class PolicySelection(BaseModel):
    policy_id: str
    policy_parameters: Dict[str, float] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_policy(self):
        _validate_policy_fields(self.policy_id, self.policy_parameters)
        return self


class SimulationConfig(BaseModel):
    population: PopulationConfig = Field(default_factory=PopulationConfig)
    policy_id: str | None = None
    policy_parameters: Dict[str, float] = Field(default_factory=dict)
    policy_bundle: List[PolicySelection] = Field(default_factory=list, max_length=2)
    target_wards: List[str] = Field(default_factory=list, max_length=25)
    rounds: int = Field(default=20, ge=1, le=100)
    seed: int = 42

    @model_validator(mode='after')
    def validate_policy_configuration(self):
        if self.policy_bundle:
            for selection in self.policy_bundle:
                _validate_policy_fields(selection.policy_id, selection.policy_parameters)
        else:
            _validate_policy_fields(self.policy_id, self.policy_parameters)
        return self

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
    size: int = Field(default=10000, ge=10000, le=10000)
    rounds: int = Field(default=20, ge=1, le=100)
    seed: int = 42


class AccessUnlockRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)
