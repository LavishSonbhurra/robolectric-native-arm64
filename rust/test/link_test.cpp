// Link and smoke test for librustlibs.a: the C++ halves of the live cxx
// bridges (cxx.cc as in libcxxbridge05, the generated minikin bridge code)
// plus this file must link against librustlibs.a with no other Rust code.
//
// minikin::rust::getScript/getJoiningType are normally ICU calls from
// libminikin_from_rust_to_cpp (ffi/IcuBridge.cpp); stubs are enough here.

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "minikin_cxx_bridge.rs.h"
#include "rust/cxx.h"

namespace minikin {
namespace rust {
int g_script_calls = 0;
uint8_t getScript(uint32_t) {  // RUST_USCRIPT_LATIN
    g_script_calls++;
    return 0;
}
uint8_t getJoiningType(uint32_t) { return 0; }  // RUST_U_JT_NON_JOINING
}  // namespace rust
}  // namespace minikin

extern "C" int rustlibs_smoke_test() {
    // cxx runtime: rust::String and rust::Vec are implemented in Rust.
    ::rust::String locale("en-US");
    ::rust::Vec<uint8_t> v;
    v.push_back(7);
    if (locale.size() != 5 || v.size() != 1 || v[0] != 7) return 1;

    // Hyphenator::new also initializes the logger (env_logger on host).
    static const uint8_t kNoPatterns[1] = {0};
    ::rust::Box<minikin::rust::Hyphenator> h = minikin::rust::load_hyphenator(
            ::rust::Slice<const uint8_t>(kNoPatterns, 0), 2, 2, ::rust::String("en"));

    // No patterns: hyphenate_with_no_pattern. A soft hyphen (U+00AD) gives a
    // break after it whose type comes from the script of the next character
    // (a Rust to C++ call); a hyphen-minus gives a break without a new hyphen.
    struct Case {
        uint16_t word[5];
        uint8_t want[5];
    } cases[] = {
            {{'a', 'b', 0x00AD, 'c', 'd'}, {0, 0, 0, 1, 0}},  // BreakAndInsertHyphen
            {{'a', 'b', '-', 'c', 'd'}, {0, 0, 0, 5, 0}},     // BreakAndDontInsertHyphen
    };
    for (const Case& c : cases) {
        uint8_t out[5];
        memset(out, 0xff, sizeof(out));
        minikin::rust::hyphenate(*h, ::rust::Slice<const uint16_t>(c.word, 5),
                                 ::rust::Slice<uint8_t>(out, 5));
        if (memcmp(out, c.want, 5) != 0) return 2;
    }
    if (minikin::rust::g_script_calls == 0) return 3;
    return 0;
}

#ifndef RUSTLIBS_TEST_NO_MAIN
int main() {
    int rc = rustlibs_smoke_test();
    printf("rustlibs smoke test: %s (%d)\n", rc == 0 ? "ok" : "FAILED", rc);
    return rc;
}
#endif
