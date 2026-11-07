$input a_position
$output v_shadowWorld

#include <bgfx_shader.sh>

void main()
{
    vec4 world = mul(u_model[0], vec4(a_position, 1.0));
    v_shadowWorld = world.xyz;
    gl_Position = mul(u_viewProj, world);
}
