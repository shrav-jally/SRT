////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// Copyright (c) 2022 - 2023 Saxonica Limited.
// This Source Code Form is subject to the terms of the Mozilla Public License,
// v. 2.0. If a copy of the MPL was not distributed with this file, You can
// obtain one at http://mozilla.org/MPL/2.0/. This Source Code Form is
// "Incompatible With Secondary Licenses", as defined by the Mozilla Public
// License, v. 2.0.
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

#ifndef CYTHON_EXCEPTION_HANDLER_H
#define CYTHON_EXCEPTION_HANDLER_H

#include "Python.h"
#include "saxonc/SaxonApiException.h"
#include <exception>
#include <string>

namespace CythonExceptionHandler {
    PyObject *SaxonApiErrorWrapper;
    void create_saxonc_api_py_exception();
    void handle_saxonc_api_exceptions();

    void create_saxonc_api_py_exception() {
        SaxonApiErrorWrapper = PyErr_NewException("saxonc.PySaxonApiError", NULL, NULL);
    }

    void handle_saxonc_api_exceptions() {
        try {
            if (PyErr_Occurred())
                ; // let the latest Python exn pass through and ignore the current one
            else
                throw;
        } catch (SaxonApiException &e) {
            const char *errorMessage = e.getMessageWithErrorCode();
            if (errorMessage == nullptr) {
                errorMessage = e.getMessage();
                if (errorMessage == nullptr) {
                    PyErr_SetString(SaxonApiErrorWrapper, "Unknown exception found");
                } else {
                    PyErr_SetString(SaxonApiErrorWrapper, errorMessage);
                }
            } else {
                PyErr_SetString(SaxonApiErrorWrapper, errorMessage);
            }
        } catch (const std::bad_alloc& exn) {
            PyErr_SetString(PyExc_MemoryError, exn.what());
        } catch (const std::bad_cast& exn) {
            PyErr_SetString(PyExc_TypeError, exn.what());
        } catch (const std::bad_typeid& exn) {
            PyErr_SetString(PyExc_TypeError, exn.what());
        } catch (const std::domain_error& exn) {
            PyErr_SetString(PyExc_ValueError, exn.what());
        } catch (const std::invalid_argument& exn) {
            PyErr_SetString(PyExc_ValueError, exn.what());
        } catch (const std::ios_base::failure& exn) {
            // Unfortunately, in standard C++ we have no way of distinguishing EOF
            // from other errors here; be careful with the exception mask
            PyErr_SetString(PyExc_IOError, exn.what());
        } catch (const std::out_of_range& exn) {
            // Change out_of_range to IndexError
            PyErr_SetString(PyExc_IndexError, exn.what());
        } catch (const std::overflow_error& exn) {
            PyErr_SetString(PyExc_OverflowError, exn.what());
        } catch (const std::range_error& exn) {
            PyErr_SetString(PyExc_ArithmeticError, exn.what());
        } catch (const std::underflow_error& exn) {
            PyErr_SetString(PyExc_ArithmeticError, exn.what());
        } catch (const std::exception& exn) {
            PyErr_SetString(PyExc_RuntimeError, exn.what());
        }
        catch (...)
        {
            PyErr_SetString(PyExc_RuntimeError, "Unknown exception");
        }
    }
}

#endif