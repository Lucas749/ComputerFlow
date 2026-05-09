__all__ = [
    # Runner — primary entry point for executing flows
    "ComputerFlowRunner",
    "RunConfig",
    "RunResult",
    "ExecutionMode",
    # SOP / action types — shared contract between recorder, compiler, runner
    "SOP",
    "SOPStep",
    "RecordedAction",
    "ActionType",
    "TargetKind",
    "Surface",
    # Low-level clients
    "LightconeClient",
    "ComputerSession",
    "ComputerKind",
    "TaskEvent",
    "KernelClient",
    "BrowserSession",
    "BrowserInfo",
    "PlaywrightResult",
    "BrevClient",
    "NIMClient",
]

_RUNNER    = ("ComputerFlowRunner", "RunConfig", "RunResult", "ExecutionMode")
_TYPES     = ("SOP", "SOPStep", "RecordedAction", "ActionType", "TargetKind", "Surface")
_LIGHTCONE = ("LightconeClient", "ComputerSession", "ComputerKind", "TaskEvent")
_KERNEL    = ("KernelClient", "BrowserSession", "BrowserInfo", "PlaywrightResult")
_BREV      = ("BrevClient", "NIMClient")


def __getattr__(name):
    if name in _RUNNER:
        from .runner import ComputerFlowRunner, RunConfig, RunResult, ExecutionMode
        return locals()[name]
    if name in _TYPES:
        from .types import SOP, SOPStep, RecordedAction, ActionType, TargetKind, Surface
        return locals()[name]
    if name in _LIGHTCONE:
        from .lightcone import LightconeClient, ComputerSession, ComputerKind, TaskEvent
        return locals()[name]
    if name in _KERNEL:
        from .kernel import KernelClient, BrowserSession, BrowserInfo, PlaywrightResult
        return locals()[name]
    if name in _BREV:
        from .brev import BrevClient, NIMClient
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
