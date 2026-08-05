# Python 装饰器

## 什么是装饰器

装饰器（Decorator）是 Python 中一种强大的功能，允许你在不修改原函数代码的情况下，动态地给函数添加新的功能。

## 装饰器的基本语法

```python
def decorator(func):
    def wrapper(*args, **kwargs):
        print("调用前")
        result = func(*args, **kwargs)
        print("调用后")
        return result
    return wrapper

@decorator
def say_hello():
    print("你好！")
```

## 装饰器的应用场景

- **日志记录**：自动记录函数调用信息
- **性能计时**：测量函数的执行时间
- **权限检查**：验证用户是否有权执行操作
- **缓存**：缓存函数的结果以提高性能

## 带参数的装饰器

```python
def repeat(n):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for _ in range(n):
                func(*args, **kwargs)
        return wrapper
    return decorator

@repeat(3)
def greet(name):
    print(f"你好，{name}！")
```

## 类装饰器

除了函数装饰器，Python 还支持类装饰器：

```python
class CountCalls:
    def __init__(self, func):
        self.func = func
        self.count = 0
    
    def __call__(self, *args, **kwargs):
        self.count += 1
        return self.func(*args, **kwargs)
```

## 总结

装饰器是 Python 中实现**面向切面编程**的重要工具，它让代码更加模块化、可重用。
