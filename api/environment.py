"""Typed doctor API; deliberate fault scenarios are opt-in and labelled."""
from typing import Literal
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from src.doctor import ROOT, check_environment


class DoctorRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['edge-tts', 'openai', 'piper', 'vieneu']
    scenario: Literal['real', 'missing_dependency', 'missing_model'] = 'real'


class Check(BaseModel):
    id: str
    label: str
    status: Literal['ready', 'missing', 'invalid', 'unverified', 'optional']
    message: str
    remedy: str


class DoctorReport(BaseModel):
    provider: str
    status: Literal['blocked', 'checks_passed']
    runtime: str
    fixture: str | None
    checks: list[Check]
    notice: str


def create_router(verification_enabled=False):
    router = APIRouter(prefix='/api/v1/environment', tags=['Environment'])

    @router.post('/doctor', response_model=DoctorReport)
    def doctor(body: DoctorRequest):
        if body.scenario != 'real' and not verification_enabled:
            raise HTTPException(404)
        if body.scenario == 'missing_model' and body.provider not in {'piper', 'vieneu'}:
            raise HTTPException(422)
        report = check_environment(body.provider, python=ROOT / '.venv' / 'bin' / 'python')
        if body.scenario != 'real':
            fixture = json.loads((ROOT / 'tests/fixtures/t03/scenarios.json').read_text())[body.scenario]
            report['fixture'] = body.scenario
            if body.scenario == 'missing_dependency':
                from src.doctor import PROVIDERS
                target = 'dependency:' + PROVIDERS[body.provider]
            else:
                target = 'model:PIPER_MODEL_PATH' if body.provider == 'piper' else 'model_validation'
            report['checks'] = [c for c in report['checks'] if c['id'] != target]
            report['checks'].append(dict(id=target, **fixture))
            report['status'] = 'blocked'
        return report

    return router
