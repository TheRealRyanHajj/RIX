$input a_position, a_normal, a_texcoord0, a_color0
$output v_color0, v_texcoord0, v_normal, v_worldPosition, v_shadowCoord

#include <bgfx_shader.sh>

uniform vec4 u_normalMatrix[3];
uniform mat4 u_shadowMatrix;

void main()
{
    vec4 world_position = mul(u_model[0], vec4(a_position, 1.0));
    gl_Position = mul(u_viewProj, world_position);
    v_worldPosition = world_position.xyz;
    v_shadowCoord = mul(u_shadowMatrix, world_position);
    v_color0 = a_color0;
    v_texcoord0 = a_texcoord0;
    v_normal = normalize(vec3(
        dot(u_normalMatrix[0].xyz, a_normal),
        dot(u_normalMatrix[1].xyz, a_normal),
        dot(u_normalMatrix[2].xyz, a_normal)));
}
