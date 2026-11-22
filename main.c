#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "pico/stdlib.h"
#include "pico/time.h"
#include "pico/bootrom.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "ws2812.pio.h"

#include "font5x8.h"

/* ---------- Configuration ---------- */
#define NUM_COLS   32
#define NUM_ROWS   8
#define NUM_LEDS   (NUM_COLS * NUM_ROWS)  /* 256 */
#define DATA_PIN   10
#define PIO_FREQ   800000.0f

#define LINE_BUF   512
#define TEXT_BUF   256

/* ---------- State ---------- */
static uint32_t pixels[NUM_LEDS];
static volatile int img_recv = 0;
static int img_idx = 0;
static uint8_t img_bytes[NUM_LEDS * 3];
static uint8_t  brightness = 128;
static uint8_t  anim_mode = 0;  /* 0=text,1=rainbow,2=pulse,3=wave,4=fire,5=matrix,6=plasma,7=sparkle,8=image,9=bounce */
static uint8_t  anim_speed = 24;
static uint32_t anim_tick = 0;
static uint64_t last_anim = 0;
static uint32_t rng = 2463534242u;

static char text_buf[TEXT_BUF];
static int  text_len = 0;
static int  scroll_x = 0;
static int  text_width = 0;
static uint8_t text_color_r = 255, text_color_g = 255, text_color_b = 255;
static uint8_t text_rainbow = 0;
static uint8_t bg_color_r = 0, bg_color_g = 0, bg_color_b = 0;
static int  text_dir = 1;  /* 1=left-to-right */
static int  vflip = 0;
static int  hflip = 0;
static int  text_baseline = 0;

static uint32_t image_buf[NUM_LEDS];

static PIO  strip_pio;
static uint strip_sm;
static uint strip_offset;

static const uint8_t sin_tab[256] = {
    128,131,134,137,140,143,146,149,152,155,158,162,165,167,170,173,
    176,179,182,185,188,190,193,196,198,201,203,206,208,211,213,215,
    218,220,222,224,226,228,230,232,234,235,237,238,240,241,243,244,
    245,246,248,249,250,250,251,252,253,253,254,254,254,255,255,255,
    255,255,255,255,254,254,254,253,253,252,251,250,250,249,248,246,
    245,244,243,241,240,238,237,235,234,232,230,228,226,224,222,220,
    218,215,213,211,208,206,203,201,198,196,193,190,188,185,182,179,
    176,173,170,167,165,162,158,155,152,149,146,143,140,137,134,131,
    128,124,121,118,115,112,109,106,103,100,97,93,90,88,85,82,
    79,76,73,70,67,65,62,59,57,54,52,49,47,44,42,40,
    37,35,33,31,29,27,25,23,21,20,18,17,15,14,12,11,
    10,9,7,6,5,5,4,3,2,2,1,1,1,0,0,0,
    0,0,0,0,1,1,1,2,2,3,4,5,5,6,7,9,
    10,11,12,14,15,17,18,20,21,23,25,27,29,31,33,35,
    37,40,42,44,47,49,52,54,57,59,62,65,67,70,73,76,
    79,82,85,88,90,93,97,100,103,106,109,112,115,118,121,124
};

/* ---------- Helpers ---------- */
static inline uint32_t pack(uint8_t r, uint8_t g, uint8_t b) {
    return ((uint32_t)g << 24) | ((uint32_t)r << 16) | ((uint32_t)b << 8);
}

static inline int idx(int x, int y) {
    if (x < 0 || x >= NUM_COLS || y < 0 || y >= NUM_ROWS) return -1;
    int px = hflip ? (NUM_COLS - 1 - x) : x;
    int py = vflip ? (NUM_ROWS - 1 - y) : y;
    return px * NUM_ROWS + py;
}

static uint8_t rand8(void) {
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return (uint8_t)(rng >> 24);
}

static void clear_pixels(void) {
    for (int i = 0; i < NUM_LEDS; i++) pixels[i] = 0;
}

static void strip_init(void) {
    strip_pio = pio0;
    strip_sm = 0;
    strip_offset = pio_add_program(strip_pio, &ws2812_program);
    ws2812_program_init(strip_pio, strip_sm, strip_offset, DATA_PIN, PIO_FREQ, false);
    clear_pixels();
}

static void strip_show(void) {
    if (brightness == 0) {
        for (int i = 0; i < NUM_LEDS; i++) pio_sm_put_blocking(strip_pio, strip_sm, 0);
        return;
    }
    for (int i = 0; i < NUM_LEDS; i++) {
        uint32_t p = pixels[i];
        uint8_t g = ((p >> 24) & 0xFF) * brightness / 255;
        uint8_t r = ((p >> 16) & 0xFF) * brightness / 255;
        uint8_t b = ((p >> 8) & 0xFF) * brightness / 255;
        pio_sm_put_blocking(strip_pio, strip_sm, pack(r, g, b));
    }
}

static int char_width(char c) {
    if (c < 32 || c > 126) return 0;
    return 5;
}

static int text_pixel_width(const char *s) {
    int w = 0;
    for (int i = 0; s[i]; i++) {
        if (s[i] == ' ') w += 3;
        else w += 6;
    }
    if (w > 0) w -= 1;
    return w;
}

static void draw_char(int x, char c, uint8_t r, uint8_t g, uint8_t b) {
    if (c < 32 || c > 126) return;
    int ci = c - 32;
    for (int row = 0; row < 8; row++) {
        uint8_t bits = font5x8[ci][row];
        for (int col = 0; col < 5; col++) {
            if (!(bits & (1 << (4 - col)))) continue;
            int px = x + col;
            if (px < 0 || px >= NUM_COLS) continue;
            uint8_t rr = r, gg = g, bb = b;
            if (text_rainbow) {
                uint8_t hue = (anim_tick * 2 + px * 8) & 0xFF;
                uint8_t region = hue / 43;
                uint8_t rem = (hue % 43) * 6;
                uint8_t p = 0, q = 255 - rem, t = rem;
                switch (region) {
                    case 0: rr=255; gg=t; bb=p; break;
                    case 1: rr=q; gg=255; bb=p; break;
                    case 2: rr=p; gg=255; bb=t; break;
                    case 3: rr=p; gg=q; bb=255; break;
                    case 4: rr=t; gg=p; bb=255; break;
                    default: rr=255; gg=p; bb=q; break;
                }
            }
            int y = row + text_baseline;
            if (y < 0 || y >= NUM_ROWS) continue;
            int i = idx(px, y);
            if (i >= 0) pixels[i] = pack(rr, gg, bb);
        }
    }
}

static void render_text(void) {
    clear_pixels();
    if (bg_color_r || bg_color_g || bg_color_b) {
        for (int i = 0; i < NUM_LEDS; i++)
            pixels[i] = pack(bg_color_r, bg_color_g, bg_color_b);
    }
    int x = scroll_x;
    for (int i = 0; i < text_len && text_buf[i]; i++) {
        char c = text_buf[i];
        if (c == ' ') { x += 3; continue; }
        draw_char(x, c, text_color_r, text_color_g, text_color_b);
        x += 6;
    }
}

/* ---------- Effects ---------- */
static void fx_rainbow(void) {
    for (int col = 0; col < NUM_COLS; col++) {
        uint8_t hue = (anim_tick + col * 8) & 0xFF;
        uint8_t r, g, b;
        uint8_t region = hue / 43;
        uint8_t rem = (hue % 43) * 6;
        uint8_t p = 0, q = 255 - rem, t = rem;
        switch (region) {
            case 0: r=255; g=t; b=p; break;
            case 1: r=q; g=255; b=p; break;
            case 2: r=p; g=255; b=t; break;
            case 3: r=p; g=q; b=255; break;
            case 4: r=t; g=p; b=255; break;
            default: r=255; g=p; b=q; break;
        }
        for (int row = 0; row < NUM_ROWS; row++) {
            int i = idx(col, row);
            if (i >= 0) pixels[i] = pack(r, g, b);
        }
    }
}

static void fx_pulse(void) {
    uint8_t phase = anim_tick & 0xFF;
    uint8_t brightness = (phase < 128) ? (phase * 2) : (255 - (phase - 128) * 2);
    uint32_t px = pack((text_color_r * brightness) / 255,
                       (text_color_g * brightness) / 255,
                       (text_color_b * brightness) / 255);
    for (int i = 0; i < NUM_LEDS; i++) pixels[i] = px;
}

static void fx_wave(void) {
    for (int col = 0; col < NUM_COLS; col++) {
        uint8_t v = sin_tab[(anim_tick + col * 4) & 0xFF];
        uint8_t r = (v * text_color_r) / 255;
        uint8_t g = (v * text_color_g) / 255;
        uint8_t b = (v * text_color_b) / 255;
        for (int row = 0; row < NUM_ROWS; row++) {
            int i = idx(col, row);
            if (i >= 0) pixels[i] = pack(r, g, b);
        }
    }
}

static void fx_fire(void) {
    for (int col = 0; col < NUM_COLS; col++) {
        if (rand8() < 80) {
            uint8_t v = 180 + (rand8() % 75);
            pixels[idx(col, NUM_ROWS - 1)] = pack(v, v / 3, 0);
        }
    }
    for (int col = 0; col < NUM_COLS; col++) {
        for (int row = 0; row < NUM_ROWS - 1; row++) {
            uint32_t p = pixels[idx(col, row + 1)];
            uint8_t r = ((p >> 16) & 0xFF);
            uint8_t g = ((p >> 24) & 0xFF);
            uint8_t b = ((p >> 8) & 0xFF);
            r = (r > 20) ? r - 20 : 0;
            g = (g > 10) ? g - 10 : 0;
            b = (b > 5) ? b - 5 : 0;
            pixels[idx(col, row)] = pack(r, g, b);
        }
        int top = idx(col, 0);
        if (top >= 0) {
            uint32_t p = pixels[top];
            pixels[top] = pack(((p >> 16) & 0xFF) * 8 / 10,
                               ((p >> 24) & 0xFF) * 8 / 10,
                               ((p >> 8) & 0xFF) * 8 / 10);
        }
    }
}

static void fx_matrix(void) {
    for (int i = 0; i < NUM_LEDS; i++) {
        uint32_t p = pixels[i];
        uint8_t r = ((p >> 16) & 0xFF) * 8 / 10;
        uint8_t g = ((p >> 24) & 0xFF) * 8 / 10;
        uint8_t b = ((p >> 8) & 0xFF) * 8 / 10;
        pixels[i] = pack(r, g, b);
    }
    if (rand8() < 40) {
        int col = rand8() % NUM_COLS;
        pixels[idx(col, 0)] = pack(0, 255, 0);
    }
    for (int col = 0; col < NUM_COLS; col++) {
        for (int row = NUM_ROWS - 1; row > 0; row--) {
            int i = idx(col, row);
            int above = idx(col, row - 1);
            if (i >= 0 && above >= 0) pixels[i] = pixels[above];
        }
        int top = idx(col, 0);
        if (top >= 0 && (rand8() < 30)) pixels[top] = 0;
    }
}

static void fx_plasma(void) {
    for (int col = 0; col < NUM_COLS; col++) {
        for (int row = 0; row < NUM_ROWS; row++) {
            uint8_t v1 = sin_tab[(col * 8 + anim_tick * 2) & 0xFF];
            uint8_t v2 = sin_tab[(row * 16 - anim_tick * 3) & 0xFF];
            uint8_t v = (v1 + v2) / 2;
            uint8_t r = sin_tab[v];
            uint8_t g = sin_tab[(v + 85) & 0xFF];
            uint8_t b = sin_tab[(v + 170) & 0xFF];
            int i = idx(col, row);
            if (i >= 0) pixels[i] = pack(r, g, b);
        }
    }
}

static void fx_sparkle(void) {
    for (int i = 0; i < NUM_LEDS; i++) {
        uint32_t p = pixels[i];
        uint8_t r = ((p >> 16) & 0xFF) * 9 / 10;
        uint8_t g = ((p >> 24) & 0xFF) * 9 / 10;
        uint8_t b = ((p >> 8) & 0xFF) * 9 / 10;
        pixels[i] = pack(r, g, b);
    }
    if (rand8() < 60) {
        int i = rand8() % NUM_LEDS;
        pixels[i] = pack(255, 255, 255);
    }
}

/* ---------- Command parser ---------- */
static void process_cmd(const char *cmd) {
    while (*cmd && (*cmd == ' ' || *cmd == '\t')) cmd++;
    if (!*cmd) return;

    if (strncmp(cmd, "TEXT", 4) == 0 && (cmd[4] == ' ' || cmd[4] == '\0')) {
        const char *p = cmd + 4;
        while (*p == ' ') p++;
        strncpy(text_buf, p, TEXT_BUF - 1);
        text_buf[TEXT_BUF - 1] = '\0';
        text_len = strlen(text_buf);
        text_width = text_pixel_width(text_buf);
        scroll_x = -text_width;
        anim_mode = 0;
        text_dir = 1;
        printf("OK TEXT=%s (width=%d)\n", text_buf, text_width);
    } else if (strncmp(cmd, "COLOR", 5) == 0 && cmd[5] == ' ') {
        int r, g, b;
        if (sscanf(cmd + 5, "%d %d %d", &r, &g, &b) == 3) {
            text_color_r = (uint8_t)r; text_color_g = (uint8_t)g; text_color_b = (uint8_t)b;
            printf("OK COLOR=%d,%d,%d\n", r, g, b);
        }
    } else if (strncmp(cmd, "BG", 2) == 0 && cmd[2] == ' ') {
        int r, g, b;
        if (sscanf(cmd + 2, "%d %d %d", &r, &g, &b) == 3) {
            bg_color_r = (uint8_t)r; bg_color_g = (uint8_t)g; bg_color_b = (uint8_t)b;
            printf("OK BG=%d,%d,%d\n", r, g, b);
        }
    } else if (strncmp(cmd, "EFFECT", 6) == 0 && cmd[6] == ' ') {
        char mode[16];
        sscanf(cmd + 6, "%15s", mode);
        if (strcmp(mode, "rainbow") == 0) anim_mode = 1;
        else if (strcmp(mode, "pulse") == 0) anim_mode = 2;
        else if (strcmp(mode, "wave") == 0) anim_mode = 3;
        else if (strcmp(mode, "fire") == 0) anim_mode = 4;
        else if (strcmp(mode, "matrix") == 0) anim_mode = 5;
        else if (strcmp(mode, "plasma") == 0) anim_mode = 6;
        else if (strcmp(mode, "sparkle") == 0) anim_mode = 7;
        else if (strcmp(mode, "text") == 0) anim_mode = 0;
        else if (strcmp(mode, "bounce") == 0) anim_mode = 9;
        else { printf("ERR: effects: text rainbow pulse wave fire matrix plasma sparkle bounce\n"); return; }
        anim_tick = 0;
        printf("OK EFFECT=%s\n", mode);
    } else if (strncmp(cmd, "BRIGHT", 6) == 0 && cmd[6] == ' ') {
        int b;
        if (sscanf(cmd + 6, "%d", &b) == 1 && b >= 0 && b <= 255) {
            if (b > 255) b = 255;
            brightness = (uint8_t)b;
            printf("OK BRIGHT=%d\n", b);
        }
    } else if (strncmp(cmd, "SPEED", 5) == 0 && cmd[5] == ' ') {
        int s;
        if (sscanf(cmd + 5, "%d", &s) == 1 && s >= 1 && s <= 255) {
            anim_speed = (uint8_t)s;
            printf("OK SPEED=%d\n", s);
        }
    } else if (strncmp(cmd, "RAINBOWTEXT", 11) == 0) {
        text_rainbow = 1;
        printf("OK rainbow text on\n");
    } else if (strncmp(cmd, "RAINBOWTEXTOFF", 14) == 0) {
        text_rainbow = 0;
        printf("OK rainbow text off\n");
    } else if (strncmp(cmd, "VFLIP", 5) == 0) {
        vflip = !vflip;
        printf("OK VFLIP=%d\n", vflip);
    } else if (strncmp(cmd, "HFLIP", 5) == 0) {
        hflip = !hflip;
        printf("OK HFLIP=%d\n", hflip);
    } else if (strncmp(cmd, "BASE", 4) == 0 && cmd[4] == ' ') {
        int b;
        if (sscanf(cmd + 4, "%d", &b) == 1 && b >= 0 && b <= 1) {
            text_baseline = b;
            printf("OK BASE=%d\n", b);
        } else {
            printf("ERR: BASE 0 or 1\n");
        }
    } else if (strncmp(cmd, "DIR", 3) == 0 && cmd[3] == ' ') {
        int d;
        if (sscanf(cmd + 3, "%d", &d) == 1) {
            text_dir = (d >= 0) ? 1 : -1;
            printf("OK DIR=%d\n", text_dir);
        }
    } else if (strncmp(cmd, "IMAGE", 5) == 0 && (cmd[5] == ' ' || cmd[5] == '\0')) {
        const char *p = cmd + 5;
        while (*p == ' ') p++;
        int idx = 0;
        while (*p && idx < NUM_LEDS) {
            while (*p && (*p == ',' || *p == ' ' || *p == '#')) p++;
            if (!isxdigit((unsigned char)*p)) break;
            unsigned int v = 0;
            int n = 0;
            while (n < 6 && isxdigit((unsigned char)*p)) {
                char ch = *p++;
                unsigned int d = (ch >= '0' && ch <= '9') ? (unsigned int)(ch - '0') :
                                 (ch >= 'a' && ch <= 'f') ? (unsigned int)(ch - 'a' + 10) :
                                 (unsigned int)(ch - 'A' + 10);
                v = (v << 4) | d;
                n++;
            }
            if (n != 6) break;
            pixels[idx++] = pack((uint8_t)((v >> 16) & 0xFF),
                                 (uint8_t)((v >> 8) & 0xFF),
                                 (uint8_t)(v & 0xFF));
        }
        if (idx > 0) {
            anim_mode = 8; /* image mode */
            printf("OK IMAGE=%d pixels\n", idx);
        } else {
            printf("ERR: IMAGE needs hex colors\n");
        }
    } else if (strcmp(cmd, "CLEAR") == 0) {
        clear_pixels();
        printf("OK clear\n");
    } else if (strcmp(cmd, "OFF") == 0) {
        clear_pixels();
        brightness = 0;
        printf("OK off\n");
    } else if (strcmp(cmd, "ON") == 0) {
        brightness = 255;
        printf("OK on\n");
    } else if (strcmp(cmd, "PING") == 0) {
        printf("PONG\n");
    } else if (strcmp(cmd, "BOOT") == 0) {
        printf("OK rebooting\n");
        fflush(stdout);
        sleep_ms(50);
        reset_usb_boot(0, 0);
    } else if (strcmp(cmd, "HELP") == 0) {
        printf("HELP Commands:\n");
        printf("  TEXT <str>       Set scrolling text\n");
        printf("  COLOR r g b      Text color\n");
        printf("  BG r g b         Background color\n");
        printf("  EFFECT <name>    text rainbow pulse wave fire matrix plasma sparkle bounce\n");
        printf("  BRIGHT <0-255>   Brightness\n");
        printf("  SPEED <1-255>    Scroll/anim speed (1=slow)\n");
        printf("  DIR <1|-1>       Scroll direction (1=left, -1=right)\n");
        printf("  VFLIP            Upside down text\n");
        printf("  HFLIP            Reversed text\n");
        printf("  BASE <0|1>       Text baseline row offset\n");
        printf("  RAINBOWTEXT      Enable rainbow colors on text\n");
        printf("  RAINBOWTEXTOFF   Disable rainbow colors on text\n");
        printf("  CLEAR            Clear display\n");
        printf("  OFF / ON         Power off/on\n");
        printf("  PING / BOOT / HELP\n");
    } else if (cmd[0]) {
        printf("ERR: unknown. Try HELP\n");
    }
}

/* ---------- Main loop ---------- */
int main(void) {
    stdio_init_all();
    sleep_ms(800);

    strip_init();
    strcpy(text_buf, "TEST  ");
    text_len = strlen(text_buf);
    text_width = text_pixel_width(text_buf);
    scroll_x = -text_width;

    printf("LED Matrix 8x32 ready\n");
    fflush(stdout);
    sleep_ms(200);

    char buf[LINE_BUF];
    int buf_idx = 0;
    last_anim = time_us_64();

    while (true) {
        if (img_recv) {
            int c = getchar_timeout_us(1000);
            if (c != PICO_ERROR_TIMEOUT) {
                if (img_idx < NUM_LEDS * 3) img_bytes[img_idx++] = (uint8_t)c;
                if (img_idx >= NUM_LEDS * 3) {
                    clear_pixels();
                    for (int y = 0; y < 8; y++) {
                        for (int x = 0; x < 32; x++) {
                            int bi = (y * 32 + x) * 3;
                            int pi = idx(x, y);
                            if (pi >= 0)
                                pixels[pi] = pack(img_bytes[bi], img_bytes[bi+1], img_bytes[bi+2]);
                        }
                    }
                    img_recv = 0;
                    anim_mode = 8;
                    printf("OK IMGB=%d\n", NUM_LEDS);
                    fflush(stdout);
                }
            }
        } else {
            int c = getchar_timeout_us(200);
            if (c != PICO_ERROR_TIMEOUT) {
                if (c == '\n' || c == '\r') {
                    buf[buf_idx] = '\0';
                    if (buf_idx > 0) process_cmd(buf);
                    buf_idx = 0;
                } else if (buf_idx < LINE_BUF - 1 && c >= 32 && c < 127) {
                    buf[buf_idx++] = (char)c;
                }
            }
        }

        uint64_t now = time_us_64();
        uint32_t interval = 1000000 / (anim_speed * 2 + 1);
        if (interval < 20000) interval = 20000;
        if (now - last_anim >= interval) {
            last_anim = now;
            anim_tick++;

            if (anim_mode == 0 || anim_mode == 9) {
                scroll_x += text_dir;
                if (anim_mode == 9) {
                    if (scroll_x <= -text_width) { scroll_x = -text_width; text_dir = 1; }
                    if (scroll_x >= 32) { scroll_x = 32; text_dir = -1; }
                } else {
                    if (scroll_x < -text_width) scroll_x = 32;
                    if (scroll_x > 32 + text_width) scroll_x = -text_width;
                }
                render_text();
            } else if (anim_mode == 1) fx_rainbow();
            else if (anim_mode == 2) fx_pulse();
            else if (anim_mode == 3) fx_wave();
            else if (anim_mode == 4) fx_fire();
            else if (anim_mode == 5) fx_matrix();
            else if (anim_mode == 6) fx_plasma();
            else if (anim_mode == 7) fx_sparkle();
            /* mode 8 = static image */

            strip_show();
        }
    }
    return 0;
}
