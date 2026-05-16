/**
* \file
* \brief MSP430 Cross-Compiler Header
* \author Alex Mykyta
* Include file for all MSP430 device variants. \n
* This include allows for code compatibility between the following compilers:
*    - MSPGCC
*    - TI Compiler
**/

#ifndef __MSP430_XC_H__
#define __MSP430_XC_H__

#ifdef __cplusplus
extern "C" {
#endif

#include <msp430.h>
#include <isr_xc.h>
#include <intrinsics_xc.h>

//--------------------------------------------------------------------------------------------------
#if defined(__GNUC__) && defined(__MSP430__)
    // MSPGCC

    // main() return value
#define MAIN_RET_t      int
#define MAIN_RETURN     return(0)

//--------------------------------------------------------------------------------------------------
#elif defined(__TI_COMPILER_VERSION__)
    // TI Compiler

    // main() return value
#define MAIN_RET_t      void
#define MAIN_RETURN     return

//--------------------------------------------------------------------------------------------------
#else
#error "Compiler not supported."
#endif

#ifdef __cplusplus
}
#endif

#endif

