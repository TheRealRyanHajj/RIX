$input v_color0, v_texcoord0, v_normal

#include <bgfx_shader.sh>

SAMPLER2D(s_texColor, 0);
uniform vec4 u_materialColor;
uniform vec4 u_materialParams;
uniform vec4 u_ambientLight;
uniform vec4 u_directionalLight;
uniform vec4 u_directionalColor;

void main()
{
    vec4 base = texture2D(s_texColor, v_texcoord0) * v_color0 * u_materialColor;
    float diffuse = max(dot(normalize(v_normal), -normalize(u_directionalLight.xyz)), 0.0);
    vec3 illumination = u_ambientLight.rgb + u_directionalColor.rgb * diffuse;
    base.rgb *= mix(vec3_splat(1.0), illumination, u_materialParams.x);
    gl_FragColor = base;
}
