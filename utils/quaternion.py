from mathutils import Quaternion
import math


def look_rotation(forward, up):

    vec_1 = forward.normalized()
    vec_2 = up.cross(vec_1).normalized()
    vec_3 = vec_1.cross(vec_2)

    m00 = vec_2.x
    m01 = vec_2.y
    m02 = vec_2.z
    m10 = vec_3.x
    m11 = vec_3.y
    m12 = vec_3.z
    m20 = vec_1.x
    m21 = vec_1.y
    m22 = vec_1.z

    num8 = (m00 + m11) + m22

    quaternion = Quaternion()

    if num8 > 0:
        #print(1)
        num = math.sqrt(num8 + 1)
        quaternion.w = num * 0.5
        num = 0.5 / num
        quaternion.x = (m12 - m21) * num
        quaternion.y = (m20 - m02) * num
        quaternion.z = (m01 - m10) * num
        return quaternion
    
    
    elif m00 >= m11 and m00 >= m22:
        #print(2)
        num7 = math.sqrt(((1 + m00) - m11) - m22)
        num4 = 0.5 / num7
        quaternion.x = 0.5 * num7
        quaternion.y = (m01 + m10) * num4
        quaternion.z = (m02 + m20) * num4
        quaternion.w = (m12 - m21) * num4
        return quaternion
     

    elif m11 > m22:
        #print(3)
        num6 = math.sqrt(((1 + m11) - m00) - m22)
        num3 = 0.5 / num6
        quaternion.x = (m10+ m01) * num3
        quaternion.y = 0.5 * num6
        quaternion.z = (m21 + m12) * num3
        quaternion.w = (m20 - m02) * num3
        return quaternion


    else:
        #print(4)
        num5 = math.sqrt(((1 + m22) - m00) - m11)
        num2 = 0.5 / num5
        quaternion.x = (m20 + m02) * num2
        quaternion.y = (m21 + m12) * num2
        quaternion.z = 0.5 * num5
        quaternion.w = (m01 - m10) * num2
        return quaternion