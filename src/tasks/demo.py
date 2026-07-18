def echo_message(message: str = "hello") -> str:
    return f"Task completed: {message}"

def failing_task() -> None:
    raise ValueError("Intentional failure for testing")

def resize_image(input_path: str, output_path: str, width: int = 100) -> str:
    ...

def noisy_task() -> str:
    print("this print should not corrupt the runner protocol")
    return "done"

def memory_hog() -> str:
    blob = bytearray(1024 * 1024 * 1024)  # 1 GB, to blow past a low RLIMIT_AS
    return str(len(blob))