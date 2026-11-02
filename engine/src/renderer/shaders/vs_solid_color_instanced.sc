$input a_position, a_normal, a_texcoord0, a_color0, i_data0, i_data1, i_data2, i_data3
$output v_color0, v_normal, v_worldPosition, v_shadowCoord

#include <bgfx_shader.sh>

uniform mat4 u_shadowMatrix;

void main()
{
    mat4 model = mtxFromCols(i_data0, i_data1, i_data2, i_data3);
    vec4 world_position = mul(model, vec4(a_position, 1.0));
    gl_Position = mul(u_viewProj, world_position);
    v_worldPosition = world_position.xyz;
    v_shadowCoord = mul(u_shadowMatrix, world_position);
    v_color0 = a_color0;
    v_normal = normalize(mul(model, vec4(a_normal, 0.0)).xyz);
}
