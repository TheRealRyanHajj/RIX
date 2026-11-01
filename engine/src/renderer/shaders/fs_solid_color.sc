$input v_color0, v_normal

#include <bgfx_shader.sh>

uniform vec4 u_materialColor;
uniform vec4 u_materialParams;
uniform vec4 u_ambientLight;
uniform vec4 u_directionalLight;
uniform vec4 u_directionalColor;

void main()
{
    vec4 base = v_color0 * u_materialColor;
    float diffuse = max(dot(normalize(v_normal), -normalize(u_directionalLight.xyz)), 0.0);
    vec3 illumination = u_ambientLight.rgb + u_directionalColor.rgb * diffuse;
    base.rgb *= mix(vec3_splat(1.0), illumination, u_materialParams.x);
    gl_FragColor = base;
}
