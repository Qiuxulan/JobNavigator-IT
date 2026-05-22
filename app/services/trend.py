from datetime import date

from app.schemas.domain import TrendEvidence, TrendSignal


class TrendService:
    @staticmethod
    def get_signal(job_role: str, horizon_months: int = 12) -> TrendSignal:
        return TrendSignal(
            job_role=job_role,
            horizon_months=horizon_months,
            short_term="flat",
            long_term="up",
            confidence=0.74,
            evidence=[
                TrendEvidence(
                    event_id="evt_001",
                    source="jd_series",
                    title="AI应用岗位近6个月需求稳中有升",
                    event_date=date(2026, 5, 1),
                    summary="基于岗位时序统计，AI应用类岗位持续增长。",
                    impact="positive",
                )
            ],
        )

