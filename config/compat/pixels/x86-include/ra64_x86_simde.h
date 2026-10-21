// RA64_PIXELS=x86: x86 SSE intrinsics on arm64, through SIMDe's portable C.
//
// The x86_64 reference build compiles Skia at SSSE3 (-mssse3), and the qemu
// x86_64 goldens run that baseline. This header stands in for the x86
// intrinsics headers so the same SSE code paths build on arm64.
//
// SIMDE_NO_NATIVE keeps SIMDe off NEON as well, so every operation follows
// SIMDe's plain C definition of the x86 instruction.
#ifndef RA64_X86_SIMDE_H
#define RA64_X86_SIMDE_H

#if !defined(__aarch64__)
#error "ra64_x86_simde.h is for arm64 builds with RA64_PIXELS=x86"
#endif

#define SIMDE_NO_NATIVE
// Skia passes shift counts that are only constant after inlining (SkNx_sse.h).
#define SIMDE_NO_CHECK_IMMEDIATE_CONSTANT
#define SIMDE_ENABLE_NATIVE_ALIASES
#include <simde/x86/ssse3.h>

// rcpps/rsqrtps are approximations whose exact bits differ between CPU
// vendors. SIMDe's portable versions are approximations of their own. qemu
// (TCG) computes them as a correctly rounded 1/x and 1/sqrt(x), so do that.
static inline simde__m128 ra64_mm_rcp_ps(simde__m128 a) {
    simde__m128_private r_, a_ = simde__m128_to_private(a);
    for (int i = 0; i < 4; i++) r_.f32[i] = 1.0f / a_.f32[i];
    return simde__m128_from_private(r_);
}
static inline simde__m128 ra64_mm_rsqrt_ps(simde__m128 a) {
    simde__m128_private r_, a_ = simde__m128_to_private(a);
    for (int i = 0; i < 4; i++) r_.f32[i] = 1.0f / __builtin_sqrtf(a_.f32[i]);
    return simde__m128_from_private(r_);
}
static inline simde__m128 ra64_mm_rcp_ss(simde__m128 a) {
    simde__m128_private r_ = simde__m128_to_private(a);
    r_.f32[0] = 1.0f / r_.f32[0];
    return simde__m128_from_private(r_);
}
static inline simde__m128 ra64_mm_rsqrt_ss(simde__m128 a) {
    simde__m128_private r_ = simde__m128_to_private(a);
    r_.f32[0] = 1.0f / __builtin_sqrtf(r_.f32[0]);
    return simde__m128_from_private(r_);
}
#undef _mm_rcp_ps
#undef _mm_rsqrt_ps
#undef _mm_rcp_ss
#undef _mm_rsqrt_ss
#define _mm_rcp_ps(a) ra64_mm_rcp_ps(a)
#define _mm_rsqrt_ps(a) ra64_mm_rsqrt_ps(a)
#define _mm_rcp_ss(a) ra64_mm_rcp_ss(a)
#define _mm_rsqrt_ss(a) ra64_mm_rsqrt_ss(a)

#endif
