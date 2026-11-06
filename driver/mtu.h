#pragma once
#include <stddef.h>

typedef struct JX05_LINK {
    unsigned short handle;
    unsigned char active;
    unsigned char request_out;
    unsigned char request_in;
    unsigned char map_pending;
    unsigned short map_next;
    unsigned long map_patches;
} JX05_LINK;

void Jx05Reset(JX05_LINK *link);
void Jx05Events(JX05_LINK *link, const unsigned char *data, size_t size);
unsigned Jx05Acl(JX05_LINK *link, unsigned char *data, size_t size, int incoming);
