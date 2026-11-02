$input v_texcoord0

#include <bgfx_shader.sh>

SAMPLER2D(s_sceneColor, 0);
uniform vec4 u_postParams;

float luminance(vec3 color)
{
    return dot(color, vec3(0.299, 0.587, 0.114));
}

void main()
{
    vec2 inverse_size = u_postParams.xy;
    vec3 center = texture2D(s_sceneColor, v_texcoord0).rgb;
    if (u_postParams.w > 0.5) {
        vec3 north = texture2D(s_sceneColor, v_texcoord0 + vec2(0.0, -inverse_size.y)).rgb;
        vec3 south = texture2D(s_sceneColor, v_texcoord0 + vec2(0.0, inverse_size.y)).rgb;
        vec3 west = texture2D(s_sceneColor, v_texcoord0 + vec2(-inverse_size.x, 0.0)).rgb;
        vec3 east = texture2D(s_sceneColor, v_texcoord0 + vec2(inverse_size.x, 0.0)).rgb;
        float contrast = max(max(abs(luminance(north) - luminance(south)),
                                 abs(luminance(west) - luminance(east))),
                             0.0);
        float blend = smoothstep(0.04, 0.20, contrast) * 0.5;
        center = mix(center, (north + south + west + east) * 0.25, blend);
    }
    vec3 mapped = vec3_splat(1.0) - exp(-center * u_postParams.z);
    mapped = pow(max(mapped, vec3_splat(0.0)), vec3_splat(1.0 / 2.2));
    gl_FragColor = vec4(mapped, 1.0);
}
