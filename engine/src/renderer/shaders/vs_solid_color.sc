$input a_position, a_normal, a_texcoord0, a_color0
$output v_color0, v_normal

#include <bgfx_shader.sh>

uniform vec4 u_normalMatrix[3];

void main()
{
    gl_Position = mul(u_modelViewProj, vec4(a_position, 1.0));
    v_color0 = a_color0;
    v_normal = normalize(vec3(
        dot(u_normalMatrix[0].xyz, a_normal),
        dot(u_normalMatrix[1].xyz, a_normal),
        dot(u_normalMatrix[2].xyz, a_normal)));
}
