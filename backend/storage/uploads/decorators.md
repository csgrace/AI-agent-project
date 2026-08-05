# Python Decorators

## Introduction

Python decorators are a powerful tool for modifying the behavior of functions or classes. They allow you to wrap another function to extend its behavior without permanently modifying it.

## How Decorators Work

A decorator is a function that takes another function as an argument and returns a new function. The syntax uses the `@` symbol.

```python
@decorator
def function():
    pass
```

This is equivalent to: `function = decorator(function)`

## Common Uses

- Logging
- Access control
- Timing functions
- Caching results
- Enforcing types

## Practical Example

```python
import time

def timer(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        print(f"{func.__name__} took {time.time() - start} seconds")
        return result
    return wrapper

@timer
def slow_function():
    time.sleep(1)
    return "Done"
```
