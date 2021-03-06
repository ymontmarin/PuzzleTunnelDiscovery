R"zzz(
#version 430 core
uniform mat4 view; // needed for normal output

in vec3 fragColor;
in float linearZ;
in vec4 vert_normal;
in vec4 world_position;
in vec2 uv;
layout(location=0) out float outDepth;
layout(location=1) out vec4 outColor;
layout(location=2) out vec2 outUV;
layout(location=3) out int outPid;
layout(location=4) out vec3 outNormal;
const float far = 20.0;
const float near = 1.0;
layout(location=16) uniform bool phong;
layout(location=17) uniform vec3 light_position;
layout(location=18) uniform sampler2D sam;
layout(location=19) uniform bool is_render_uv_mapping;
const vec3 ambient = vec3(0.4, 0.4, 0.4);
const vec3 diffuse = vec3(0.6, 0.6, 0.6);
// const vec4 light_position = vec4(0.0, 5.0, 0.0, 1.0);
void main() {
    vec3 mColor = fragColor;
    if ((!is_render_uv_mapping) && length(texture(sam, uv).xyz) > 0.0) {
        // mColor = vec3(0.0, length(texture(sam, uv).xyz), 0.0);
        // mColor = vec3(0.0, 1.0, 0.0); // Keep the weight uniform for larger region
        mColor.y += length(texture(sam, uv).xyz); // Prefer More concentrated heatmap.
    }
    if (phong) {
	vec4 light_dir = vec4(light_position, 1.0) - world_position;
	vec4 normal = normalize(vert_normal);
	float c = clamp(dot(light_dir, normal), 0.0, 1.0);
	outColor = vec4((c * diffuse + ambient) * mColor, 1.0);
	// outColor = vec4(c, 0.0, 0.0, 1.0);
	// outColor = vec4(abs(normal.xyz), 1.0);
    } else {
        outColor = vec4(mColor, 1.0);
    }
    outUV = uv;
    outDepth = linearZ;
    outPid = int(gl_PrimitiveID);
    outNormal = normalize((view * vert_normal).xyz);
    // outPid = 1;
}
)zzz";
