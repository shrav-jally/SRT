#if !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)
#include "detail/common.h"
#warning "Including 'common.h' is deprecated. It will be removed in v3.0. Use 'pybind11.h'."

#else
#error "This file should not be included when either TORCH_STABLE_ONLY or TORCH_TARGET_VERSION is defined."
#endif  // !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)
