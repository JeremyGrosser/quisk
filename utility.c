#include <Python.h>
#ifdef MS_WINDOWS
#include <windows.h>
#else
#include <stdlib.h>
#include <sys/time.h>
#endif
#include <complex.h>
#include "quisk.h"

// Access to config file attributes.
// NOTE:  These must be called only from the main (GUI) thread,
//        not from the sound thread.

QUISK_EXPORT long QuiskGetConfigLong(const char * name, long deflt)
{  // return deflt for failure.  Accept int or float.
  long res;
  PyObject * attr;  
  if (!quisk_pyConfig || PyErr_Occurred()) {
    return deflt;
  }
  attr = PyObject_GetAttrString(quisk_pyConfig, name);
  if (attr) {
    res = PyInt_AsUnsignedLongMask(attr);  // This works for floats too!
    Py_DECREF(attr);
    return res;		// success
  }
  else {
    PyErr_Clear();
  }
  return deflt;		// failure
}

QUISK_EXPORT double QuiskGetConfigDouble(const char * name, double deflt)
{  // return deflt for failure.  Accept int or float.
  double res;
  PyObject * attr;  

  if (!quisk_pyConfig || PyErr_Occurred())
    return deflt;
  attr = PyObject_GetAttrString(quisk_pyConfig, name);
  if (attr) {
    res = PyFloat_AsDouble(attr);
    Py_DECREF(attr);
    return res;		// success
  }
  else {
    PyErr_Clear();
  }
  return deflt;		// failure
}

QUISK_EXPORT char * QuiskGetConfigString(const char * name, char * deflt)
{  // return deflt for failure.
  char * res;
  PyObject * attr;  

  if (!quisk_pyConfig || PyErr_Occurred())
    return deflt;
  attr = PyObject_GetAttrString(quisk_pyConfig, name);
  if (attr) {
    res = PyString_AsString(attr);
    Py_DECREF(attr);
    if (res)
      return res;		// success
    else
      PyErr_Clear();
  }
  else {
    PyErr_Clear();
  }
  return deflt;		// failure
}

QUISK_EXPORT double QuiskTimeSec(void)
{  // return time in seconds as a double
#ifdef MS_WINDOWS
	FILETIME ft;
	ULARGE_INTEGER ll;

	GetSystemTimeAsFileTime(&ft);
	ll.LowPart  = ft.dwLowDateTime;
	ll.HighPart = ft.dwHighDateTime;
	return (double)ll.QuadPart * 1.e-7;
#else
	struct timeval tv;

	gettimeofday(&tv, NULL);
	return (double)tv.tv_sec + tv.tv_usec * 1e-6;
#endif
}

QUISK_EXPORT void QuiskSleepMicrosec(int usec)
{
#ifdef MS_WINDOWS
	int msec = (usec + 500) / 1000;		// convert to milliseconds
	if (msec < 1)
		msec = 1;
	Sleep(msec);
#else
	struct timespec tspec;
	tspec.tv_sec = usec / 1000000;
	tspec.tv_nsec = (usec - tspec.tv_sec * 1000000) * 1000;
	nanosleep(&tspec, NULL);
#endif
}
