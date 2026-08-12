//#include "saxonc/UserFunctionHandler.h"
#include "Python.h"
#include "saxonc/XdmValue.h"
#include "saxonc/XdmNode.h"

extern "C" PyObject * CythonUserFunctionHandler;


typedef enum saxonTypeEnum {
  enumNode,
  enumString,
  enumInteger,
  enumDouble,
  enumFloat,
  enumBool,
  enumArrXdmValue
} PRIMITIVE_TYPE;


std::map<std::string, saxonTypeEnum> typeMap = {
{"node", enumNode},
{"Q{http://www.w3.org/2001/XMLSchema}string", enumString},
{"Q{http://www.w3.org/2001/XMLSchema}duration", enumString},
{"Q{http://www.w3.org/2001/XMLSchema}dateTime",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}date", enumString},
{"Q{http://www.w3.org/2001/XMLSchema}gYearMonth", enumString},
{"Q{http://www.w3.org/2001/XMLSchema}gYear",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}gMonthDay",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}time",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}integer",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}double",enumDouble},
{"Q{http://www.w3.org/2001/XMLSchema}decimal",enumDouble},
{"Q{http://www.w3.org/2001/XMLSchema}float",enumFloat},
{"Q{http://www.w3.org/2001/XMLSchema}boolean",enumBool},

{"Q{http://www.w3.org/2001/XMLSchema}gDay",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}gMonth",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}hexBinary",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}base64Binary",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}anyURI",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}QName",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}NOTATION",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}numeric",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}nonPositiveInteger",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}negativeInteger",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}long",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}int",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}short",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}byte",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}nonNegativeInteger",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}positiveInteger",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}unsignedLong",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}unsignedInt",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}unsignedShort",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}unsignedByte",enumInteger},
{"Q{http://www.w3.org/2001/XMLSchema}normalizedString",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}token",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}anyType",enumString},
{"Q{http://www.w3.org/2001/XMLSchema}anySimpleType",enumString},
{"[xdmvalue", enumArrXdmValue}

};

void * makeXdmValueFromPythonObject(PyObject * result){
    graal_isolatethread_t *thread1 = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);

    PyTypeObject * typeObj = Py_TYPE(result);

    if(typeObj != nullptr) {

       const char* c_typeObjStr = typeObj->tp_name;
       std::string typeObjStr = std::string(c_typeObjStr);
       std::string prefix("PyXdm");


       if (getenv("SAXONC_DEBUG_FLAG")) {
            fprintf(stderr, "We are in a CythonUserFunctionHandler type= %s\n", c_typeObjStr);
            fflush(stdout);
       }

       if(typeObjStr.find(prefix) != std::string::npos) {
            //We have a PyXdm object
            long resulti = PyLong_AsLong(PyObject_CallMethodNoArgs(result, PyUnicode_FromString("_get_underlying_int_value")));
            return (void *)resulti;

       } else if (PyLong_Check(result)) {
            long valueL = PyLong_AsLong(result);
            int64_t longValueRef = j_makeLongValue(thread1, valueL);
            return (void *)longValueRef;
        } else if (PyFloat_Check(result)) {
            double valueD = PyFloat_AsDouble(result);
            int64_t doubleValueRef = j_makeDoubleValue(thread1, valueD);
            return (void *)doubleValueRef;
        } else if(PyBool_Check(result)) {
            int truth = PyObject_IsTrue(result);
            if (truth < 0) {
                return nullptr;
            }
            int64_t boolValueRef = j_makeBooleanValue(thread1, truth);
            return (void *)boolValueRef;

        } else if(PyUnicode_Check(result)) {
            //TODO clauses required for other encodings
            const char* ss = PyUnicode_AsUTF8(result);
            if (ss == NULL) {
                return nullptr;
            }
            saxon_error_t r = SAXON_ERROR_DEFAULT;
            int64_t stringValueRef = j_makeStringValue(thread1, (char *)ss, nullptr, &r);

            if (r.status != SAXON_OK) {
                //TODO maybe we should be throwing some exception
                return (void *)nullptr;
            }


            return (void *)stringValueRef;

        } else if(PyList_Check(result)) {
            Py_ssize_t sizeL = PyList_Size(result);

            if (sizeL > INT_MAX || sizeL < INT_MIN) {
                if (getenv("SAXONC_DEBUG_FLAG")) {
                    fprintf(stderr, "OVerflow error for the size of the list\n");
                    fflush(stdout);
                }
                return nullptr;
            }

            int rv_arr_length = (int) sizeL;

            //TODO create XdmArray
            void * accumulatorValue = (void *)createProcessorDataWithCapacity(SaxonProcessor::sxn_environ->thread, rv_arr_length);



            for(Py_ssize_t j = 0; j < sizeL; j++) {
                PyObject* item = PyList_GetItem(result, j);

                void * rawItemValue = makeXdmValueFromPythonObject(item);
                addProcessorValue(SaxonProcessor::sxn_environ->thread, accumulatorValue, rawItemValue);
                j_handles_destroy(SaxonProcessor::sxn_environ->thread, rawItemValue);
            }

            saxon_error_t r = SAXON_ERROR_DEFAULT;
            void * arrayValue = (void *) j_makeXdmArray(thread1, (void *)accumulatorValue, &r);
            j_handles_destroy(thread1, (void *)accumulatorValue);

            if (r.status != SAXON_OK) {
                //TODO maybe we should be throwing some exception
                return (void *)nullptr;
            }
            return arrayValue;

        } else if(PyDict_Check(result)) {
            PyObject *key, *value;
            Py_ssize_t pos = 0;

            Py_ssize_t  pmapSize = PyDict_Size(result);

            if (pmapSize > INT_MAX || pmapSize < INT_MIN) {
                if (getenv("SAXONC_DEBUG_FLAG")) {
                    fprintf(stderr, "OVerflow error for the size of the map\n");
                    fflush(stdout);
                }
                return nullptr;
            }

            int rv_map_length = (int) pmapSize;

              int64_t mapDataRef = j_create_mapDataWithCapacity(thread1, rv_map_length);

            while (PyDict_Next(result, &pos, &key, &value)) {
                // key and value are borrowed references
                const char* k = PyUnicode_AsUTF8(key);
                /*if (getenv("SAXONC_DEBUG_FLAG")) {
                    printf("key = %s\n", k);
                }*/

                void * valueii = makeXdmValueFromPythonObject(value);
                saxon_error_t r = SAXON_ERROR_DEFAULT;
                void * keyii = (void *)j_makeStringValue(thread1, (char *)k, nullptr, &r);

                j_addMapPair(thread1, (void *)mapDataRef,
                                 (void *)keyii,
                                 (void *)valueii);


                j_handles_destroy(thread1, (void *)valueii);
                j_handles_destroy(thread1, (void *)keyii);
            }

            void * xdmmapRef = (void *)j_makeXdmMap(thread1, (void *)mapDataRef);

            j_handles_destroy(thread1, (void *)mapDataRef);

            return xdmmapRef;



        } else if(PySet_Check(result)) {
            Py_ssize_t ssetSize = PySet_Size(result);

            if (ssetSize > INT_MAX || ssetSize < INT_MIN) {
                if (getenv("SAXONC_DEBUG_FLAG")) {
                    fprintf(stderr, "OVerflow error for the size of the set\n");
                    fflush(stdout);
                }
                return nullptr;
            }

            int rv_set_length = (int) ssetSize;

            if(rv_set_length == 0) {
                //create empty sequence
                return nullptr;
            }

            PyObject *itemii;

            PyObject *iter = PyObject_GetIter(result);
            if (!iter) {
                // handle error
            }

            void * xdmsetRef = (void *)createProcessorDataWithCapacity(thread1, rv_set_length);

            while ((itemii = PyIter_Next(iter))) {
                void * valueii = makeXdmValueFromPythonObject(itemii);
                addProcessorValue(thread1, xdmsetRef,valueii);

                j_handles_destroy(thread1, (void *)valueii);
                Py_DECREF(itemii);
            }
            Py_DECREF(iter);

            return xdmsetRef;
        } else if(PyIter_Check(result)){
            // PyIter are treated as XdmValues
            if (getenv("SAXONC_DEBUG_FLAG")) {
                 fprintf(stderr, "OVerflow error for the size of the set\n");
                 fflush(stdout);
            }
            void * resultVoidValue  = (void *)createProcessorData(thread1);

            PyObject *item;
            while ((item = PyIter_Next(result))) {
                void * valueii = makeXdmValueFromPythonObject(item);
                // Use item
                if(valueii != nullptr) {
                    addProcessorValue(thread1, resultVoidValue,valueii);
                	j_handles_destroy(thread1, valueii);
                } else {
                    // The item is not in a form we can handle, therefore ignore. Or maybe we should report error?
                }
                Py_DECREF(item);
            }

            return resultVoidValue;

        } else if(PyGen_Check(result)){
            // PyGen are treated as XdmValues
            void * resultVoidValue  = (void *)createProcessorData(thread1);
            PyObject *item = NULL;

            while ((item = PyIter_Next(result)) != NULL) {
                 void * valueii = makeXdmValueFromPythonObject(item);
                // Use item
                if(valueii != nullptr) {
                    addProcessorValue(thread1, resultVoidValue,valueii);
                	j_handles_destroy(thread1, valueii);
                } else {
                    // The item is not in a form we can handle, therefore ignore. Or maybe we should report error?
                }
                Py_DECREF(item);
            }
            return resultVoidValue;

        } else if(PyTuple_Check(result)) {
            Py_ssize_t size = PyTuple_Size(result);

            void * resultVoidValue  = (void *)createProcessorData(thread1);

            for (Py_ssize_t i = 0; i < size; i++) {
                PyObject *item = PyTuple_GetItem(result, i);
                 void * valueii = makeXdmValueFromPythonObject(item);
                // Use item
                if(valueii != nullptr) {
                    addProcessorValue(thread1, resultVoidValue,valueii);
                    j_handles_destroy(thread1, valueii);
                } else {
                    // The item is not in a form we can handle, therefore ignore. Or maybe we should report error?
                }
            }
            return resultVoidValue;
        }



    }


    return nullptr;



}

PyObject *makePythonValue(void * proc, void * value){
    graal_isolatethread_t *thread = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);
    int typeRef = j_getXdmObjectType(thread, value);

    allocFn fn = operator new;

    if (typeRef == SXN_EXCEPTION) {

                //throw SaxonApiException();

        //zend_throw_exception(zend_ce_exception, "Error found in converting arguments", 0);
        return nullptr;
    }

    XDM_TYPE xdm_type = static_cast<XDM_TYPE>(typeRef);

    saxon_error_t r = SAXON_ERROR_DEFAULT;

    if (xdm_type == XDM_ATOMIC_VALUE) {

        char * primType = j_getPrimitiveTypeName(thread,(void *)fn, value);

                //XdmAtomicValue * aitem = (XdmAtomicValue *) (value->getHead());
                //const char * primType = aitem->getPrimitiveTypeName();

                if (getenv("SAXONC_DEBUG_FLAG")) {
                  std::cerr<<"Primitive type = "<< primType<<std::endl;
                }

                saxonTypeEnum typeValue;

                if(primType == NULL) {
                    typeValue = typeMap["Q{http://www.w3.org/2001/XMLSchema}anySimpleType"];
                } else {
                    typeValue = typeMap[primType];
                    operator delete(primType);
                }

        long bvalue;
        long lnumber;
        double dvalue;
        char * astri = nullptr;
        PyObject * unicodeStr;

        switch (typeValue) {
            case saxonTypeEnum::enumBool:
              bvalue = (long)j_getBooleanValue(thread, value, &r);
              if (r.status != SAXON_OK) {
                //TODO IF error found return false. Review this action
                Py_RETURN_NONE;
              }
              return PyBool_FromLong(bvalue);
              break;
            case saxonTypeEnum::enumInteger:
              lnumber = j_getLongValue(thread, (void *)value, &r);
              if (r.status != SAXON_OK) {
                //TODO Maybe We should throw an exception if this fails
                Py_RETURN_NONE;
              }
              return PyLong_FromLong(lnumber);
              break;
            case saxonTypeEnum::enumString:
              astri = getStringValueForXdmItem(thread,(void *)fn, value, NULL, &r);
              if (r.status != SAXON_OK) {
                Py_RETURN_NONE;
              }
              unicodeStr = PyUnicode_FromString(astri);
              operator delete(astri);
              return unicodeStr;
              break;
            case saxonTypeEnum::enumDouble:
            case saxonTypeEnum::enumFloat:
              dvalue = j_getDoubleValue(thread, value, &r);
              if(r.status != SAXON_OK) {
                Py_RETURN_NONE;
              }
              return PyFloat_FromDouble(dvalue);
              break;

            default:
                if (getenv("SAXONC_DEBUG_FLAG")) {
                  std::cerr<<"Python internal: type not found"<< std::endl;
                }
                astri = getStringValueForXdmItem(thread,(void *)fn, value, NULL, &r);
                if (r.status != SAXON_OK) {
                    //Error found
                    Py_RETURN_NONE;
                }
                unicodeStr = PyUnicode_FromString(astri);
                operator delete(astri);
                return unicodeStr;
                break;

        }
    } else if (xdm_type == XDM_NODE) {

        //TODO shift creation of XdmNode to the python code
        //TODO create unit test
        int64_t copiedValue = (int64_t)j_copy_handles(SaxonProcessor::sxn_environ->thread, value);
        PyObject * nxdmItem = PyObject_CallMethodOneArg((PyObject *) proc, PyUnicode_FromString("convert_c_obj"), PyLong_FromLong(copiedValue));

        return nxdmItem;


      }  else if (xdm_type == XDM_MAP) {

         graal_isolatethread_t *thread = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);
        int count = j_xdmMap_size(thread, (void *)value);
        //int count = mitem->mapSize();

        if (getenv("SAXONC_DEBUG_FLAG")) {
          std::cerr<<"PythonValue: XDMMap size="<<count<<std::endl;
        }

        ///// creating Python dict array
        //zend_array *ret = zend_new_array(count);
        //zend_ulong idx = 0;
        //XdmAtomicValue ** aKeys = mitem->keys();

        //graal_isolatethread_t *thread = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);
        long long *rawKeys = j_xdmMap_keys(thread,(void *)fn, (void *)value);
        saxon_error_t r = SAXON_ERROR_DEFAULT;
        long long * rawMapValues = j_xdmMap_values(thread,(void *)fn, (void *)value, &r);


        if(r.status != SAXON_OK) {
            return nullptr;
        }
        //char * ss = nullptr;

          if (getenv("SAXONC_DEBUG_FLAG")) {
            std::cerr<<"PHPValue: XDMMap before loop call"<<std::endl;
          }

        PyObject *dict = PyDict_New();
        if (!dict) return NULL;

        for (int j = 0; j < count; j++) {
          //XdmValue * avaluej =mitem->get(aKeys[j]);
          //todo add encoding instead of NULL, get the encoding from the Java code
          //ss = getStringValueForXdmItem(thread,(void *)fn, (void *)rawKeys[j], NULL);
          PyObject * retkeyvalj = makePythonValue(proc, (void *)rawKeys[j]);


          PyObject * retvalj = makePythonValue(proc, (void *)rawMapValues[j]);

          if (!retkeyvalj || !retvalj) {
            Py_XDECREF(retkeyvalj);
            Py_XDECREF(retvalj);
            Py_DECREF(dict);
            return NULL;
          }

          if (PyDict_SetItem(dict, retkeyvalj, retvalj) < 0) {
                      Py_DECREF(retkeyvalj);
                      Py_DECREF(retvalj);
                      Py_DECREF(dict);
                      return NULL;
          }
          Py_DECREF(retkeyvalj);
          Py_DECREF(retvalj);


          //operator delete(ss);

        }
        //delete [] aKeys;


        for(int j = 0; j < count; j++) {
          j_handles_destroy(thread, (void *)rawKeys[j]);
          j_handles_destroy(thread, (void *)rawMapValues[j]);
        }
        operator delete(rawKeys);
        operator delete(rawMapValues);
        /*delete mitem;
        delete value;*/

        return dict;

      } else if (xdm_type == XDM_ARRAY) {

        graal_isolatethread_t *thread = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);
        int count = j_xdmArray_arrayLength(thread,(void *)value);

        if (getenv("SAXONC_DEBUG_FLAG")) {
          std::cerr<<"PythonValue: XDMarray size="<<count<<std::endl;
        }

        ///// creating Python array

        long idx = 0;
        int64_t avaluej =-1;
        PyObject *  retvali = nullptr;
        PyObject *list = PyList_New(count);
        if (!list) return NULL;


        for (int j = 0; j < count; j++) {

          avaluej =
              j_xdmArray_get(thread, (void *)value, j, &r);

          if(r.status != SAXON_OK) {
            j_handles_destroy(thread, (void *)avaluej);
            Py_RETURN_NONE;
          }
          //XdmValue * avaluej =aitem->get(j);
          //itemi->incrementRefCount();

          retvali = makePythonValue(proc, (void *)avaluej);
          // Steals reference to value
          PyList_SetItem(list, j, retvali);

          Py_DECREF(retvali);

          j_handles_destroy(thread, (void *)avaluej);


          idx++;
        }
        return list;

    } else if(xdm_type == XDM_VALUE) {
        allocFn fn = operator new;
        graal_isolatethread_t *thread1 = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);
        long long *rawValues = makeArrayFromXdmValue2(thread1, (void *)fn, (void *)value);

        int count = (int) rawValues[0];
        if (getenv("SAXONC_DEBUG_FLAG")) {
            std::cerr<<"PHPValue: XDMValue size="<<count<<std::endl;
        }

        PyObject *tuple = PyTuple_New(count);

        PyObject *list = PyList_New(count);
        if (!list) return NULL;

        for(int i=1; i <= count; i++) {
            PyObject * itemii = makePythonValue(proc, (void *)rawValues[i]);

            PyTuple_SetItem(tuple, i-1, itemii);
            j_handles_destroy(thread1, (void *)rawValues[i]);
        }


        operator delete(rawValues);

        return tuple;
    }
    Py_RETURN_NONE;
}

void * userFunctionPythonNativeCall(void * proc, void * func, int useNativeTypes, int numOfArguments,  void ** argumentsi){
    //PyObject_CallNoArgs((PyObject *)func);
    XdmValue ** arguments;
    //PyObject* argsList = nullptr;
    PyObject* arg = nullptr;
    PyObject *args = nullptr;
    int err;

    allocFn fn = operator new;

    if(func == nullptr || ((PyObject *)func) == Py_None){
        return nullptr;
    }

    /*if (!PyCallable_Check(func)) {
        PyErr_SetString(PyExc_TypeError, "The function object is not callable");
        return NULL;
    } */


    if (getenv("SAXONC_DEBUG_FLAG")) {
          fprintf(stdout, "We are in a **Cython** function. calling Python logic \n");
          if(proc == NULL) {
            fprintf(stdout, "Python proc is NULL");
          }
        std::cerr << "arguments count="<< numOfArguments << std::endl;
        fprintf(stdout, "user function python proc pointer= %p func=%p\n", (void *)proc, (void *)func);

        fprintf(stdout, "Num of arguments= %i \n", numOfArguments);
    }

    PyObject* kwargs = PyDict_New();
    if (!kwargs) return NULL;
    Py_INCREF((PyObject *) proc);
    // Add key-value pairs
    PyDict_SetItemString(kwargs, "processor", (PyObject *) proc);

    args = PyTuple_New(numOfArguments);   // n = number of arguments


    if(numOfArguments>0) {

        graal_isolatethread_t *thread = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);

        //argsList = PyList_New(numOfArguments);

        PyObject * argi = nullptr;


        PyObject *pArgs;

        /*if(PyCallable_Check((PyObject *)proc)) {
             fprintf(stdout, "Processor is not callable in Python");
             return nullptr;
        } */

        XdmValue * tempValue = nullptr;


    if (getenv("SAXONC_DEBUG_FLAG")) {

        fprintf(stdout, "Num of arguments now= %i \n", numOfArguments);
    }



        for(Py_ssize_t i = 0; i < numOfArguments; i++) {
            if (getenv("SAXONC_DEBUG_FLAG")) {
                fprintf(stdout, "Making XdmValue ref=%ld.\n", (long)argumentsi[i]);
            }

            long argxi = (long)argumentsi[i]; //TODO we may need to copy arguments: j_copy_handles(thread, (void *)argumentsi[i]);

            if(useNativeTypes) {
                argi = makePythonValue(proc, argumentsi[i]);
            } else {
                //TODO how to we handle an emptySequence??
                argi = PyObject_CallMethodOneArg((PyObject *) proc, PyUnicode_FromString("convert_c_obj"), PyLong_FromLong(argxi));
            }

            if (getenv("SAXONC_DEBUG_FLAG")) {
                fprintf(stdout, "cython user function checkpoint 0\n");
            }

            if(argi == nullptr) {
                if (getenv("SAXONC_DEBUG_FLAG")) {
                    PyErr_Print();
                }

                return nullptr;
            }

            Py_INCREF(argi);        // Ensure ownership
            PyTuple_SET_ITEM(args, i, argi);  // steals reference
        }

    }
    //PyErr_Print();
    if (getenv("SAXONC_DEBUG_FLAG")) {
        fprintf(stdout, "cython user function checkpoint 1\n");
    }

    /*
    if (PyFunction_Check(obj)) {
        PyObject* name_obj = PyObject_GetAttrString(obj, "__name__");
        if (name_obj && PyUnicode_Check(name_obj)) {
            const char* name = PyUnicode_AsUTF8(name_obj);
            // use name
        }
        Py_XDECREF(name_obj);
    }
    */

    if (!PyCallable_Check((PyObject *)func)) {
        PyErr_SetString(PyExc_TypeError, "The function object is not callable");
        return NULL;
    }

    if (!PyTuple_Check(args)) {
        PyErr_SetString(PyExc_TypeError, "arguments to the function not defined correctly");
        return NULL;
    }


    PyObject* result = PyObject_Call((PyObject *)func, args, kwargs);
    if (getenv("SAXONC_DEBUG_FLAG")) {
      PyErr_Print();
        if(result != nullptr) {
            PyErr_Print();
            fprintf(stdout, "user function in c code python returned a value\n");
        }
    }

    if(args != nullptr){
        //TODO decrement ref counts
        Py_DECREF(args);
    }

    Py_DECREF(kwargs);

    if(result == nullptr) {
        if (getenv("SAXONC_DEBUG_FLAG")) {
            fprintf(stdout, "user function result is NULL\n");
        }
        //PyErr_SetString(PyExc_TypeError, "The call to the function object  failed");
        //TODO We have entered this path because we have an error in calling the function.
        //TODO we should not raise a python error here, but create a Java exception which
        //TODO should be picked up later by the caller we hope
        /*PyObject *type, *value, *traceback;
        PyErr_Fetch(&type, &value, &traceback);
        PyErr_NormalizeException(&type, &value, &traceback);
        const char *msg = PyUnicode_AsUTF8(PyObject_Str(value)); */
        //Py_DECREF(type);
        //Py_DECREF(value);
        //Py_DECREF(traceback);
        // fprintf(stdout, msg);
        return nullptr;
    }

    if(result == Py_None ) {
        return nullptr;
    }

    void * resulti = makeXdmValueFromPythonObject(result);

    return  (void *)resulti;
}

void setNativePythonFunction(){
    graal_isolatethread_t *thread = SaxonProcessor::getOrAttachCurrentThread(SaxonProcessor::sxn_environ);
    j_setPythonNative(thread);
    nativePythonFn fn1 = userFunctionPythonNativeCall;

    j_setIndirectFunctionForPythonNativeCall(thread, (void *)fn1);


}
