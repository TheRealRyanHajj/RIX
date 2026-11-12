$input a_position, a_normal, a_texcoord0, a_color0, a_tangent, a_indices, a_weight
$output v_color0, v_normal, v_worldPosition, v_shadowCoord

#include <bgfx_shader.sh>
uniform vec4 u_normalMatrix[3];
uniform mat4 u_shadowMatrix;
uniform vec4 u_boneRows[192];

vec3 skin(vec3 value, float w, uvec4 indices, vec4 weights)
{
    vec4 v = vec4(value, w);
    vec3 result = vec3(0.0, 0.0, 0.0);
    int b = int(indices.x) * 3;
    result += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * weights.x;
    b = int(indices.y) * 3;
    result += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * weights.y;
    b = int(indices.z) * 3;
    result += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * weights.z;
    b = int(indices.w) * 3;
    result += vec3(dot(u_boneRows[b], v), dot(u_boneRows[b+1], v), dot(u_boneRows[b+2], v)) * weights.w;
    return result;
}

void main()
{
    vec3 position = skin(a_position, 1.0, a_indices, a_weight);
    vec3 normal = normalize(skin(a_normal, 0.0, a_indices, a_weight));
    vec4 world_position = mul(u_model[0], vec4(position, 1.0));
    gl_Position = mul(u_viewProj, world_position);
    v_worldPosition = world_position.xyz;
    v_shadowCoord = mul(u_shadowMatrix, world_position);
    v_color0 = a_color0;
    v_normal = normalize(vec3(dot(u_normalMatrix[0].xyz, normal), dot(u_normalMatrix[1].xyz, normal), dot(u_normalMatrix[2].xyz, normal)));
}
