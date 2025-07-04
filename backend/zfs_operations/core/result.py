from typing import Generic, TypeVar, Union, Optional, Callable, Any, cast
from dataclasses import dataclass

T = TypeVar('T')
E = TypeVar('E', bound=Exception)
U = TypeVar('U')


@dataclass(frozen=True)
class Result(Generic[T, E]):
    """Result type for explicit error handling without exceptions"""
    _value: Optional[T] = None
    _error: Optional[E] = None
    
    def __post_init__(self):
        # Ensure exactly one of value or error is set
        if (self._value is None) == (self._error is None):
            raise ValueError("Result must have exactly one of value or error")
    
    @classmethod
    def success(cls, value: T) -> 'Result[T, E]':
        """Create a successful result"""
        return cls(_value=value)
    
    @classmethod
    def failure(cls, error: E) -> 'Result[T, E]':
        """Create a failed result"""
        return cls(_error=error)
    
    @property
    def is_success(self) -> bool:
        """Check if result is successful"""
        return self._error is None
    
    @property
    def is_failure(self) -> bool:
        """Check if result is a failure"""
        return self._error is not None
    
    @property
    def value(self) -> T:
        """Get the success value (raises ValueError if result is failure)"""
        if self.is_failure:
            raise ValueError("Cannot get value from failed result")
        return cast(T, self._value)
    
    @property
    def error(self) -> E:
        """Get the error (raises ValueError if result is success)"""
        if self.is_success:
            raise ValueError("Cannot get error from successful result")
        return cast(E, self._error)
    
    def value_or(self, default: T) -> T:
        """Get value or return default if failure"""
        return cast(T, self._value) if self.is_success else default
    
    def value_or_else(self, func: Callable[[E], T]) -> T:
        """Get value or compute default from error if failure"""
        return cast(T, self._value) if self.is_success else func(cast(E, self._error))
    
    def map(self, func: Callable[[T], U]) -> 'Result[U, E]':
        """Transform the success value while preserving failure"""
        if self.is_success:
            try:
                return Result.success(func(cast(T, self._value)))
            except Exception as e:
                return Result.failure(e)  # type: ignore
        return Result.failure(cast(E, self._error))
    
    def map_error(self, func: Callable[[E], Exception]) -> 'Result[T, Exception]':
        """Transform the error while preserving success"""
        if self.is_failure:
            return Result.failure(func(cast(E, self._error)))
        return Result.success(cast(T, self._value))
    
    def flat_map(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """Chain operations that return Results (monadic bind)"""
        if self.is_success:
            return func(cast(T, self._value))
        return Result.failure(cast(E, self._error))
    
    def and_then(self, func: Callable[[T], 'Result[U, E]']) -> 'Result[U, E]':
        """Alias for flat_map for better readability"""
        return self.flat_map(func)
    
    def or_else(self, func: Callable[[E], 'Result[T, E]']) -> 'Result[T, E]':
        """Provide alternative result if this one failed"""
        if self.is_failure:
            return func(cast(E, self._error))
        return self
    
    def filter(self, predicate: Callable[[T], bool], error_factory: Callable[[], E]) -> 'Result[T, E]':
        """Filter success value with predicate"""
        if self.is_success and not predicate(cast(T, self._value)):
            return Result.failure(error_factory())
        return self
    
    def to_dict(self) -> dict:
        """Convert result to dictionary for serialization"""
        if self.is_success:
            return {
                'success': True,
                'value': self._value,
                'error': None
            }
        else:
            error = cast(E, self._error)
            error_dict = error.to_dict() if hasattr(error, 'to_dict') else str(error)
            return {
                'success': False,
                'value': None,
                'error': error_dict
            }
    
    def __bool__(self) -> bool:
        """Result is truthy if successful"""
        return self.is_success
    
    def __str__(self) -> str:
        """String representation of result"""
        if self.is_success:
            return f"Success({self._value})"
        return f"Failure({self._error})"
    
    def __repr__(self) -> str:
        """Detailed string representation"""
        return self.__str__()


# Convenience functions for creating results
def success(value: T) -> Result[T, Any]:
    """Create a successful result"""
    return Result.success(value)


def failure(error: E) -> Result[Any, E]:
    """Create a failed result"""
    return Result.failure(error)


# Utility functions for working with multiple results
def collect_results(results: list[Result[T, E]]) -> Result[list[T], E]:
    """Collect multiple results into a single result containing a list"""
    values = []
    for result in results:
        if result.is_failure:
            return Result.failure(result.error)
        values.append(result.value)
    return Result.success(values)


def first_success(results: list[Result[T, E]]) -> Optional[Result[T, E]]:
    """Return the first successful result, or None if all failed"""
    for result in results:
        if result.is_success:
            return result
    return None


def first_failure(results: list[Result[T, E]]) -> Optional[Result[T, E]]:
    """Return the first failed result, or None if all succeeded"""
    for result in results:
        if result.is_failure:
            return result
    return None 