/**
 * \file
 * \brief MSP430 Intrinsics cross-compatibility Header
 * \author Alex Mykyta
 * This include allows for code compatibility between the following compilers:
 *    - MSPGCC
 *    - TI Compiler
 *
 * The following intrinsics are enforced by this header:
 *
 *    - __no_operation()
 *    - __disable_interrupt()
 *    - __enable_interrupt()
 *    - __get_SR_register()
 *    - __get_interrupt_state ()
 *    - __set_interrupt_state (sv)
 *    - __get_SP_register()          or  _get_SP_register()
 *    - __set_SP_register(src)       or _set_SP_register(src)
 *    - __bic_SR_register(x)
 *    - __bis_SR_register(x)
 *    - __bic_SR_register_on_exit(x)
 *    - __bis_SR_register_on_exit(x)
 *    - __delay_cycles (delay)       or _delay_cycles (delay)
 *    - __swap_bytes (v)
 *    - __bcd_add_short(op1, op2)
 *    - __bcd_add_long(op1, op2)
 *
 **/
#ifndef _INTRINSICS_XC_H
#define _INTRINSICS_XC_H

/*

 *
 */

#ifndef __MSP430_XC_H__
#error Do not include this file directly. Include msp430_xc.h instead
#endif

//--------------------------------------------------------------------------------------------------
#if defined(__GNUC__) && defined(__MSP430__)

#define __get_SR_register       __read_status_register
#define __get_SP_register       __read_stack_pointer
#define __set_SP_register()     __write_stack_pointer(x)
#define _delay_cycles(x)        __delay_cycles(x)


#define __bcd_add_short(op1, op2)           \
        (__extension__({                        \
            unsigned int __op1 = op1;           \
            unsigned int __op2 = op2;           \
            unsigned int __result;              \
            __asm__("mov %1, %0\n\t"            \
                    "clrc\n\t"                  \
                    "dadd %2, %0"               \
                    :"=r"(__result)             \
                    :"r"(__op1),"r"(__op2)      \
                    :                           \
            );                                  \
            __result;                           \
        }))


#define __bcd_add_long(op1, op2)            \
        (__extension__({                        \
            unsigned long int __op1 = op1;      \
            unsigned long int __op2 = op2;      \
            unsigned long int __result;         \
            __asm__("mov %A1, %A0\n\t"          \
                    "mov %B1, %B0\n\t"          \
                    "clrc\n\t"                  \
                    "dadd %A2, %A0\n\t"         \
                    "dadd %B2, %B0\n\t"         \
                    :"=r"(__result)             \
                    :"r"(__op1),"r"(__op2)      \
                    :                           \
            );                                  \
            __result;                           \
        }))

// Disable incompatible TI intrinsics
#define __even_in_range(x,y)    (x)
#define _never_executed

// Disable IAR attributes
#define __no_init
#define __data16

//--------------------------------------------------------------------------------------------------
#elif defined(__TI_COMPILER_VERSION__)

#define __get_interrupt_state       _get_interrupt_state
#define __set_interrupt_state(x)    _set_interrupt_state(x)


//--------------------------------------------------------------------------------------------------
#else
#error "Compiler not supported."
#endif


#endif
