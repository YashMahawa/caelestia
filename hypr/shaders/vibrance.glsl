#version 300 es
precision mediump float;

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D tex;

// Selective saturation (vibrance) and contrast values for AMOLED feel
const float VIB_VIBRANCE = 0.38;     // Boost level for unsaturated colors
const float VIB_SATURATION = 1.12;   // Global saturation multiplier
const float VIB_CONTRAST = 1.04;     // Contrast multiplier
const float VIB_BRIGHTNESS = 1.0;    // Brightness offset

void main() {
    vec4 pixColor = texture(tex, v_texcoord);
    vec3 color = pixColor.rgb;

    // 1. Contrast & Brightness Enhancement
    color = (color - 0.5) * VIB_CONTRAST + 0.5 + (VIB_BRIGHTNESS - 1.0);
    color = clamp(color, 0.0, 1.0);

    // 2. Vibrance (Selective Saturation)
    // Convert to luma using standard BT.601 coefficients
    float luma = dot(color, vec3(0.299, 0.587, 0.114));

    float mn = min(min(color.r, color.g), color.b);
    float mx = max(max(color.r, color.g), color.b);
    float sat = (mx - mn) / (mx + 1e-6);

    // Boost unsaturated pixels more than already saturated ones
    float boost = 1.0 + VIB_VIBRANCE * (1.0 - sat);
    color = mix(vec3(luma), color, boost * VIB_SATURATION);

    fragColor = vec4(clamp(color, 0.0, 1.0), pixColor.a);
}
