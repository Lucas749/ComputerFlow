__all__ = [
    # Runner — primary entry point
    "ComputerFlowRunner",
    "FlowRequest",
    "FlowResult",
    "RunOptions",
    # Action / SOP types
    "RecordedAction",
    "SOPStep",
    "ActionType",
    "TargetKind",
    "Surface",
    "RunTarget",
    "ExecutionStrategy",
    # Low-level clients (direct use / testing)
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

_RUNNER    = ("ComputerFlowRunner", "FlowRequest", "FlowResult", "RunOptions")
_TYPES     = (
    "RecordedAction", "SOPStep", "ActionType",
    "TargetKind", "Surface", "RunTarget", "ExecutionStrategy",
)
_LIGHTCONE = ("LightconeClient", "ComputerSession", "ComputerKind", "TaskEvent")
_KERNEL    = ("KernelClient", "BrowserSession", "BrowserInfo", "PlaywrightResult")
_BREV      = ("BrevClient", "NIMClient")


def __getattr__(name):
    if name in _RUNNER:
        from .runner import ComputerFlowRunner, FlowRequest, FlowResult, RunOptions
        return locals()[name]
    if name in _TYPES:
        from .types import (
            RecordedAction, SOPStep, ActionType,
            TargetKind, Surface, RunTarget, ExecutionStrategy,
        )
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
