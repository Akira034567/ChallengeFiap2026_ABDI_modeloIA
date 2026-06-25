import numpy as np

# Rapid Entire Body Assessment
def REBA(pred_jts):
    # Coordinates
    coords = pred_jts.astype(float)
    coords[1:, 2] = coords[1:, 2] - coords[0, 2]
    coords[0 , 2] = 0
    
    # vector index
    trunk = (17, 0)
    leg_left1, leg_left2 = (4, 5), (5, 6)
    leg_right1, leg_right2 = (1, 2), (2, 3)
    neck = (10, 17)
    arm_left1, arm_left2 = (11, 12), (12, 13)
    arm_right1, arm_right2 = (14, 15), (15, 16)
    
    # vectors
    trunk_vec = coords[trunk[1], :] - coords[trunk[0], :]
    leg_left1_vec = coords[leg_left1[1], :] - coords[leg_left1[0], :]
    leg_left2_vec = coords[leg_left2[1], :] - coords[leg_left2[0], :]
    leg_right1_vec = coords[leg_right1[1], :] - coords[leg_right1[0], :]
    leg_right2_vec = coords[leg_right2[1], :] - coords[leg_right2[0], :]
    neck_vec = coords[neck[1], :] - coords[neck[0], :]
    arm_left1_vec = coords[arm_left1[1], :] - coords[arm_left1[0], :]
    arm_left2_vec = coords[arm_left2[1], :] - coords[arm_left2[0], :]
    arm_right1_vec = coords[arm_right1[1], :] - coords[arm_right1[0], :]
    arm_right2_vec = coords[arm_right2[1], :] - coords[arm_right2[0], :]
    
    
    # We define a theta caculator
    def theta(a, b):
        the = np.arccos((a * b).sum() / np.linalg.norm(a) / np.linalg.norm(b))
        return the / np.pi * 180
    
    # angles
    theta_trunk = max(theta(trunk_vec, leg_left1_vec), theta(trunk_vec, leg_left2_vec))
    theta_neck = theta(neck_vec, trunk_vec)
    theta_leg = max(theta(leg_left1_vec, leg_left2_vec), theta(leg_right1_vec, leg_right2_vec))
    theta_uparm = max(theta(arm_left1_vec, trunk_vec), theta(arm_right1_vec, trunk_vec))
    theta_lowarm = max(theta(arm_left1_vec, arm_left2_vec), theta(arm_right1_vec, arm_right2_vec))
    
    # score
    # trunk
    if theta_trunk < 1:
        score_trunk = 1
    elif theta_trunk < 20:
        score_trunk = 2
    elif theta_trunk < 60:
        score_trunk = 3
    else:
        score_trunk = 4
    # neck
    if theta_neck < 20:
        score_neck = 1
    else:
        score_neck = 2
    # leg
    score_leg = 2
    if theta_leg > 30 and theta_leg < 60:
        score_leg += 1
    elif theta_leg > 60:
        score_leg += 2
    # Upper arms
    score_uparm = 1
    if theta_uparm < 20:
        score_uparm += 1
    elif theta_uparm < 45:
        score_uparm += 2
    elif theta_uparm < 90:
        score_uparm += 3
    else:
        score_uparm += 4
    # lower arm
    if theta_lowarm < 100 and theta_lowarm > 60:
        score_lowarm = 1
    else:
        score_lowarm = 2
    # wrist
    score_wrist = 2
    
    # tables
    tableA = [[[1,2,3,4], [2,3,4,5], [2,4,5,6], [3,5,6,7], [4,6,7,8]],
              [[1,2,3,4], [3,4,5,6], [4,5,6,7], [5,6,7,8], [6,7,8,9]], 
              [[3,3,5,6], [4,5,6,7], [5,6,7,8], [6,7,8,9], [7,8,9,9]]]
    tableA = np.array(tableA)
    tableB = [[[1,2,3], [1,2,3], [3,4,5], [4,5,5], [6,7,8], [7,8,8]],
              [[1,2,3], [2,3,4], [4,5,5], [5,6,7], [7,8,8], [8,9,9]]]
    tableB = np.array(tableB)
    tableC = [[1,1,1,2,3,3,4,5,6,7,7,7], [1,2,2,3,4,4,5,6,6,7,7,8], [2,3,3,3,4,5,6,7,7,8,8,8], [3,4,4,4,5,6,7,8,8,9,9,9],
              [3,4,4,4,5,6,7,8,8,9,9,9], [6,6,6,7,8,8,9,9,10,10,10,10], [7,7,7,8,9,9,9,10,10,11,11,11], [8,8,8,9,10,10,10,10,10,11,11,11],
              [9,9,9,10,10,10,11,11,11,12,12,12], [10,10,10,11,11,11,11,12,12,12,12,12], [11,11,11,11,12,12,12,12,12,12,12,12], [12,12,12,12,12,12,12,12,12,12,12,12]]
    tableC = np.array(tableC)

    # risk level
    scoreA = tableA[score_neck - 1, score_trunk - 1, score_leg - 1]
    scoreB = tableB[score_lowarm - 1, score_uparm - 1, score_wrist - 1]
    REBAscore = tableC[scoreA - 1, scoreB - 1]
    if REBAscore <= 1:
        risk = 'Negligible'
    elif REBAscore <= 3:
        risk = 'Low'
    elif REBAscore <= 7:
        risk = 'Medium'
    elif REBAscore <= 10:
        risk = 'High'
    else:
        risk = 'Very high'
    
    return risk, REBAscore