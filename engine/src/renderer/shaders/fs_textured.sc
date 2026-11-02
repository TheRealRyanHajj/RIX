$input v_color0, v_texcoord0, v_normal, v_worldPosition, v_shadowCoord

#include <bgfx_shader.sh>

SAMPLER2D(s_texColor, 0);
uniform vec4 u_materialColor;
uniform vec4 u_materialParams;
uniform vec4 u_ambientLight;
uniform vec4 u_directionalLight;
uniform vec4 u_directionalColor;
uniform vec4 u_cameraPosition;
uniform vec4 u_renderParams;
uniform vec4 u_shadowParams;
SAMPLER2D(s_shadowMap, 1);

float shadow_visibility(vec4 coordinate)
{
    if (u_renderParams.y < 0.5) {
        return 1.0;
    }
    vec3 projected = coordinate.xyz / coordinate.w;
    if (projected.x < 0.0 || projected.x > 1.0 || projected.y < 0.0 ||
        projected.y > 1.0 || projected.z < 0.0 || projected.z > 1.0) {
        return 1.0;
    }
    float visibility = 0.0;
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            float stored = texture2D(
                s_shadowMap,
                projected.xy + vec2(float(x), float(y)) * u_shadowParams.xy).r;
            visibility += projected.z - u_shadowParams.z <= stored ? 1.0 : 0.0;
        }
    }
    return visibility / 9.0;
}

vec3 shade(vec3 base, vec3 surface_normal, vec3 world_position)
{
    vec3 normal = normalize(surface_normal);
    vec3 light_direction = -normalize(u_directionalLight.xyz);
    float diffuse = max(dot(normal, light_direction), 0.0);
    vec3 legacy = base * (u_ambientLight.rgb + u_directionalColor.rgb * diffuse);
    vec3 view_direction = normalize(u_cameraPosition.xyz - world_position);
    vec3 halfway_direction = normalize(light_direction + view_direction);
    float roughness = clamp(u_materialParams.z, 0.04, 1.0);
    float shininess = mix(256.0, 4.0, roughness * roughness);
    float specular = pow(max(dot(normal, halfway_direction), 0.0), shininess);
    vec3 f0 = mix(vec3_splat(0.04), base, u_materialParams.y);
    vec3 diffuse_color = base * (1.0 - u_materialParams.y);
    vec3 pbr = u_ambientLight.rgb * base
             + u_directionalColor.rgb * (diffuse_color * diffuse + f0 * specular);
    return mix(legacy, pbr, u_renderParams.x);
}

void main()
{
    vec4 base = texture2D(s_texColor, v_texcoord0) * v_color0 * u_materialColor;
    vec3 illuminated = shade(base.rgb, v_normal, v_worldPosition);
    illuminated *= mix(0.35, 1.0, shadow_visibility(v_shadowCoord));
    base.rgb = mix(base.rgb, illuminated, u_materialParams.x)
             + base.rgb * u_materialParams.w;
    gl_FragColor = base;
}
