class SpineForgeError(Exception):
    """Base for expected domain failures."""


class InvalidSourceError(SpineForgeError):
    pass


class SecurityError(InvalidSourceError):
    pass


class ParsingError(SpineForgeError):
    pass


class UnresolvedDependencyError(SpineForgeError):
    pass


class AmbiguousMatchError(SpineForgeError):
    pass


class UnsupportedVersionError(SpineForgeError):
    pass
