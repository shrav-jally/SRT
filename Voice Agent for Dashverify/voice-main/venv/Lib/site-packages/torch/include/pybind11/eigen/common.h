#if !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)
// Copyright (c) 2023 The pybind Community.

#pragma once

// Common message for `static_assert()`s, which are useful to easily
// preempt much less obvious errors.
#define PYBIND11_EIGEN_MESSAGE_POINTER_TYPES_ARE_NOT_SUPPORTED                                    \
    "Pointer types (in particular `PyObject *`) are not supported as scalar types for Eigen "     \
    "types."

#else
#error "This file should not be included when either TORCH_STABLE_ONLY or TORCH_TARGET_VERSION is defined."
#endif  // !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)
