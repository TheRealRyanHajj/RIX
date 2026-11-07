$input a_position, a_normal, a_texcoord0, a_color0, a_tangent, i_data0, i_data1, i_data2, i_data3
$output v_color0, v_texcoord0, v_normal, v_worldPosition, v_shadowCoord, v_tangent, v_bitangent

#include <bgfx_shader.sh>

uniform mat4 u_shadowMatrix;
uniform vec4 u_uvScale[3];
uniform vec4 u_uvAtlas[6];
uniform vec4 u_textureParams;

vec2 mapped_uv(vec2 uv, vec3 normal)
{
    float mode = u_textureParams.x;
    if (mode > 1.5 && mode < 2.5) {
        int face = normal.z > 0.5 ? 0 : normal.z < -0.5 ? 1
                 : normal.x > 0.5 ? 2 : normal.x < -0.5 ? 3
                 : normal.y > 0.5 ? 4 : 5;
        return u_uvAtlas[face].xy + uv * u_uvAtlas[face].zw;
    }
    if (mode > 0.5 && mode < 1.5) {
        vec2 scale = abs(normal.x) > 0.5 ? u_uvScale[0].xy
                   : abs(normal.y) > 0.5 ? u_uvScale[1].xy
                   : u_uvScale[2].xy;
        return uv * scale;
    }
    if (mode > 2.5) return uv * u_uvScale[0].xy;
    return uv;
}

float model_handedness(mat4 model)
{
    vec3 axis_x = mul(model, vec4(1.0, 0.0, 0.0, 0.0)).xyz;
    vec3 axis_y = mul(model, vec4(0.0, 1.0, 0.0, 0.0)).xyz;
    vec3 axis_z = mul(model, vec4(0.0, 0.0, 1.0, 0.0)).xyz;
    return dot(cross(axis_x, axis_y), axis_z) < 0.0 ? -1.0 : 1.0;
}

void main()
{
    mat4 model = mtxFromCols(i_data0, i_data1, i_data2, i_data3);
    vec4 world_position = mul(model, vec4(a_position, 1.0));
    gl_Position = mul(u_viewProj, world_position);
    v_worldPosition = world_position.xyz;
    v_shadowCoord = mul(u_shadowMatrix, world_position);
    v_color0 = a_color0;
    v_texcoord0 = mapped_uv(a_texcoord0, a_normal);
    v_normal = normalize(mul(model, vec4(a_normal, 0.0)).xyz);
    v_tangent = normalize(mul(model, vec4(a_tangent.xyz, 0.0)).xyz);
    v_tangent = normalize(v_tangent - v_normal * dot(v_normal, v_tangent));
    v_bitangent = normalize(cross(v_normal, v_tangent))
                * a_tangent.w * model_handedness(model);
}
