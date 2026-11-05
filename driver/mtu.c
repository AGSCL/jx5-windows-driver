#include "mtu.h"

static unsigned short Read16(const unsigned char *p)
{
    return (unsigned short)(p[0] | ((unsigned short)p[1] << 8));
}

void Jx05Reset(JX05_LINK *link)
{
    link->handle = 0;
    link->active = link->request_out = link->request_in = 0;
}

void Jx05Events(JX05_LINK *link, const unsigned char *data, size_t size)
{
    static const unsigned char address[6] = {0x7e, 0xf3, 0xc6, 0x01, 0xfc, 0xb7};
    size_t pos, i;
    /* A lost/partial event could hide handle reuse: stop matching until rediscovery. */
    for (pos = 0; pos < size;) {
        if (size - pos < 2 || (size_t)data[pos + 1] + 2 > size - pos) {
            Jx05Reset(link);
            return;
        }
        pos += (size_t)data[pos + 1] + 2;
    }
    for (pos = 0; pos < size; pos += (size_t)data[pos + 1] + 2) {
        const unsigned char *p = data + pos;
        if (p[0] == 0x05) {
            if (p[1] != 4 || Read16(p + 3) == link->handle) Jx05Reset(link);
        } else if (p[0] == 0x03) {
            if (p[1] != 11 || Read16(p + 3) == link->handle) Jx05Reset(link);
        } else if (p[0] == 0x3e && p[1] >= 1 && p[2] == 0x29) {
            /* Enhanced Connection Complete v2 is not decoded by this prototype. */
            Jx05Reset(link);
        } else if (p[0] == 0x3e && p[1] >= 1 &&
                   (p[2] == 0x01 || p[2] == 0x0a)) {
            if ((p[2] == 0x01 && p[1] != 19) || (p[2] == 0x0a && p[1] != 31)) {
                Jx05Reset(link);
                continue;
            }
            if (p[3] != 0) continue;
            if (Read16(p + 4) == link->handle) Jx05Reset(link);
            for (i = 0; i < 6 && p[8 + i] == address[i]; ++i) {}
            if (i == 6 && p[6] == 0 && p[7] == 0 && Read16(p + 4) <= 0x0eff) {
                Jx05Reset(link);
                link->handle = Read16(p + 4);
                link->active = 1;
            }
        } else if (p[0] == 0x0e && p[1] >= 4 && Read16(p + 3) == 0x0c03) {
            Jx05Reset(link);
        }
    }
}

unsigned Jx05Acl(JX05_LINK *link, unsigned char *data, size_t size, int incoming)
{
    size_t pos;
    unsigned changed = 0;
    if (!link->active || size > 4096) return 0;
    /* shortcut: fragmented USB/HCI MTU exchanges pass through; validate on hardware. */
    for (pos = 0; pos < size;) {
        if (size - pos < 4 || (size_t)Read16(data + pos + 2) + 4 > size - pos) return 0;
        pos += (size_t)Read16(data + pos + 2) + 4;
    }
    for (pos = 0; pos < size; pos += (size_t)Read16(data + pos + 2) + 4) {
        unsigned char *p = data + pos;
        unsigned short flags = Read16(p);
        unsigned short mtu;
        unsigned pb = (flags >> 12) & 3;
        if ((flags & 0x0fff) != link->handle || (flags & 0xc000) ||
            (pb != 0 && pb != 2) || Read16(p + 2) != 7 ||
            Read16(p + 4) != 3 || Read16(p + 6) != 4) continue;
        mtu = Read16(p + 9);
        if (mtu < 23 || mtu > 517) continue;
        if (p[8] == 0x02) {
            if (incoming) link->request_in = 1;
            else link->request_out = 1;
        } else if (p[8] == 0x03) {
            if (incoming ? !link->request_out : !link->request_in) continue;
            if (incoming) link->request_out = 0;
            else link->request_in = 0;
        } else continue;
        if (mtu != 23) {
            p[9] = 23;
            p[10] = 0;
            ++changed;
        }
    }
    return changed;
}
