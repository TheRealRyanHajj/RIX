$input a_position, a_indices, a_weight
$output v_shadowWorld

#include <bgfx_shader.sh>
uniform vec4 u_boneRows[192];

void main()
{
    vec4 v = vec4(a_position, 1.0);
    vec3 position = vec3(0.0, 0.0, 0.0);
    int b = int(a_indices.x) * 3;
    position += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * a_weight.x;
    b = int(a_indices.y) * 3;
    position += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * a_weight.y;
    b = int(a_indices.z) * 3;
    position += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * a_weight.z;
    b = int(a_indices.w) * 3;
    position += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * a_weight.w;
    vec4 world = mul(u_model[0], vec4(position, 1.0));
    v_shadowWorld = world.xyz;
    gl_Position = mul(u_viewProj, world);
}
