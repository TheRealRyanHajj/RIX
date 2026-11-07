$input v_texcoord0

#include <bgfx_shader.sh>

uniform vec4 u_skyTop;
uniform vec4 u_skyHorizon;
uniform vec4 u_skyBottom;
uniform vec4 u_skyParams;
uniform vec4 u_skyCamera[3];
SAMPLER2D(s_skyPanorama, 7);
SAMPLERCUBE(s_skyCubemap, 8);

void main()
{
    vec2 screen = vec2(v_texcoord0.x * 2.0 - 1.0, 1.0 - v_texcoord0.y * 2.0);
    vec3 direction = normalize(u_skyCamera[2].xyz
                             + u_skyCamera[0].xyz * screen.x * u_skyParams.z
                             + u_skyCamera[1].xyz * screen.y * u_skyParams.w);
    float angle = u_skyParams.y;
    float cosine = cos(angle);
    float sine = sin(angle);
    direction.xz = vec2(direction.x * cosine - direction.z * sine,
                        direction.x * sine + direction.z * cosine);
    vec3 color;
    if (u_skyParams.x < 0.5) {
        float height = direction.y;
        color = height >= 0.0
            ? mix(u_skyHorizon.rgb, u_skyTop.rgb, smoothstep(0.0, 1.0, height))
            : mix(u_skyHorizon.rgb, u_skyBottom.rgb, smoothstep(0.0, 1.0, -height));
    } else if (u_skyParams.x < 1.5) {
        vec2 uv = vec2(atan2(direction.x, -direction.z) * 0.1591549431 + 0.5,
                       acos(clamp(direction.y, -1.0, 1.0)) * 0.3183098862);
        color = texture2D(s_skyPanorama, uv).rgb;
    } else {
        color = textureCube(s_skyCubemap, direction).rgb;
    }
    gl_FragColor = vec4(color * u_skyTop.a, 1.0);
}
