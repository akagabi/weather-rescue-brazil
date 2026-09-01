class BillingGuardError(RuntimeError):
    pass

_FORBIDDEN = ("desert-ant", "desert_ant", "desertant")

def assert_personal(value: str) -> None:
    low = value.lower()
    for token in _FORBIDDEN:
        if token in low:
            raise BillingGuardError(
                f"'{value}' looks like a Desert Ant identifier; this project bills PERSONAL accounts only."
            )
