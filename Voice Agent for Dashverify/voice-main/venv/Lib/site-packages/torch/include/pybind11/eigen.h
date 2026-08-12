#if !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)
/*
    pybind11/eigen.h: Transparent conversion for dense and sparse Eigen matrices

    Copyright (c) 2016 Wenzel Jakob <wenzel.jakob@epfl.ch>

    All rights reserved. Use of this source code is governed by a
    BSD-style license that can be found in the LICENSE file.
*/

#pragma once

#include "eigen/matrix.h"

#else
#error "This file should not be included when either TORCH_STABLE_ONLY or TORCH_TARGET_VERSION is defined."
#endif  // !defined(TORCH_STABLE_ONLY) && !defined(TORCH_TARGET_VERSION)
