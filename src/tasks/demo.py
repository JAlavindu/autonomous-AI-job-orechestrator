def echo_message(message: str = "hello") -> str:
    return f"Task completed: {message}"

def failing_task() -> None:
    raise ValueError("Intentional failure for testing")

def resize_image(input_path: str, output_path: str, width: int = 100) -> str:
    ...