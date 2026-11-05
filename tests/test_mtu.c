#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../driver/mtu.h"

static const unsigned char connected[] = {
    0x3e,19,1,0,0,2,0,0,0x7e,0xf3,0xc6,1,0xfc,0xb7,6,0,0,0,200,0,0
};
static const unsigned char request[] = {0,0x22,7,0,3,0,4,0,2,64,0};
static const unsigned char response[] = {0,0x22,7,0,3,0,4,0,3,64,0};

static void Connect(JX05_LINK *link)
{
    Jx05Reset(link);
    Jx05Events(link, connected, sizeof(connected));
    assert(link->active && link->handle == 0x200);
}

int main(void)
{
    JX05_LINK link;
    unsigned char p[600], original[600];
    size_t n;
    unsigned i;
    unsigned long random = 42;
    Connect(&link);
    memcpy(p, request, sizeof(request));
    assert(Jx05Acl(&link, p, sizeof(request), 0) == 1 && p[9] == 23);
    memcpy(p, response, sizeof(response));
    assert(Jx05Acl(&link, p, sizeof(response), 1) == 1 && p[9] == 23);
    assert(!link.request_out);
    memcpy(p, response, sizeof(response));
    assert(Jx05Acl(&link, p, sizeof(response), 1) == 0 && p[9] == 64);
    /* Peripheral-initiated exchange, and an already-minimal request. */
    memcpy(p, request, sizeof(request)); p[9] = 23;
    assert(Jx05Acl(&link, p, sizeof(request), 1) == 0);
    memcpy(p, response, sizeof(response));
    assert(Jx05Acl(&link, p, sizeof(response), 0) == 1 && p[9] == 23);
    /* Other handles, CIDs, opcodes, malformed lengths and fragments are unchanged. */
    for (i = 0; i < 6; ++i) {
        Connect(&link); memcpy(p, request, sizeof(request));
        switch (i) {
        case 0: p[0] = 1; break;
        case 1: p[6] = 5; break;
        case 2: p[8] = 0x12; break;
        case 3: p[2] = 8; break;
        case 4: p[1] = 0x12; break;
        case 5: p[9] = 22; break;
        }
        memcpy(original, p, sizeof(request));
        assert(Jx05Acl(&link, p, sizeof(request), 0) == 0);
        assert(memcmp(original, p, sizeof(request)) == 0);
    }
    Connect(&link); memcpy(p, request, sizeof(request)); p[11] = 0;
    assert(Jx05Acl(&link, p, 12, 0) == 0 && p[9] == 64);
    memcpy(p + 11, request, sizeof(request));
    assert(Jx05Acl(&link, p, 22, 0) == 2 && p[9] == 23 && p[20] == 23);
    for (n = 0; n < sizeof(request); ++n) {
        Connect(&link); memcpy(p, request, sizeof(request));
        assert(Jx05Acl(&link, p, n, 0) == 0 && p[9] == 64);
    }
    Connect(&link);
    { const unsigned char gone[] = {5,4,0,0,2,0x16}; Jx05Events(&link, gone, sizeof(gone)); }
    assert(!link.active);
    Connect(&link); memcpy(p, connected, sizeof(connected)); p[8] ^= 1;
    Jx05Events(&link, p, sizeof(connected)); assert(!link.active);
    Connect(&link); memset(p, 0, 13); p[0] = 3; p[1] = 11; p[4] = 2;
    Jx05Events(&link, p, 13); assert(!link.active);
    Connect(&link); p[0] = 0x3e; p[1] = 1; p[2] = 0x29;
    Jx05Events(&link, p, 3); assert(!link.active);
    Connect(&link);
    { const unsigned char reset[] = {0x0e,4,1,3,0x0c,0}; Jx05Events(&link, reset, sizeof(reset)); }
    assert(!link.active);
    for (n = 1; n < sizeof(connected); ++n) {
        Connect(&link); Jx05Events(&link, connected, n); assert(!link.active);
    }
    Connect(&link); memcpy(p, connected, sizeof(connected)); p[4] = 1; p[8] ^= 1;
    Jx05Events(&link, p, sizeof(connected)); assert(link.active && link.handle == 0x200);
    Jx05Reset(&link); memcpy(p, connected, sizeof(connected)); p[7] = 1;
    Jx05Events(&link, p, sizeof(connected)); assert(!link.active);
    memset(p, 0, 33); memcpy(p, connected, 14); p[1] = 31; p[2] = 0x0a;
    Jx05Events(&link, p, 33); assert(link.active);
    /* Exact-sized fuzz allocations under AddressSanitizer check parser boundaries. */
    for (i = 0; i < 100000; ++i) {
        unsigned char *exact;
        random = random * 1664525UL + 1013904223UL;
        n = (size_t)(random % sizeof(p));
        for (size_t j = 0; j < n; ++j) {
            random = random * 1664525UL + 1013904223UL;
            p[j] = (unsigned char)(random >> 24);
        }
        exact = (unsigned char *)malloc(n ? n : 1);
        assert(exact); memcpy(exact, p, n);
        Connect(&link); Jx05Events(&link, exact, n);
        Connect(&link); (void)Jx05Acl(&link, exact, n, i & 1);
        free(exact);
    }
    puts("MTU tests passed (including 100000 malformed/random buffers).");
    return 0;
}
