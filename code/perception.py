import numpy as np
import cv2

# Identify pixels above the threshold
# Threshold of RGB > 160 does a nice job of identifying ground pixels only
def navigable_thresh(img, rgb_thresh=(160, 160, 160)):
    # Create an array of zeros same xy size as img, but single channel
    color_select = np.zeros_like(img[:,:,0])
    # Require that each pixel be above all three threshold values in RGB
    # above_thresh will now contain a boolean array with "True"
    # where threshold was met
    above_thresh = (img[:,:,0] > rgb_thresh[0]) \
                & (img[:,:,1] > rgb_thresh[1]) \
                & (img[:,:,2] > rgb_thresh[2])
    # Index the array of zeros with the boolean array and set to 1
    color_select[above_thresh] = 1
    # Return the binary image
    return color_select


def rock_thresh(img):
    
    # Convert BGR to HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # define range of yellow color in HSV
    lower_yellow = np.array([50,100,100]) 
    upper_yellow = np.array([255,255,255])

    # Threshold the HSV image to get only blue colors
    yellowMask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    
    return yellowMask

# Define a function to convert from image coords to rover coords
def rover_coords(binary_img):
    # Identify nonzero pixels
    ypos, xpos = binary_img.nonzero()
    # Calculate pixel positions with reference to the rover position being at the 
    # center bottom of the image.  
    x_pixel = -(ypos - binary_img.shape[0]).astype(np.float)
    y_pixel = -(xpos - binary_img.shape[1]/2 ).astype(np.float)
    return x_pixel, y_pixel


# Define a function to convert to radial coords in rover space
def to_polar_coords(x_pixel, y_pixel):
    # Convert (x_pixel, y_pixel) to (distance, angle) 
    # in polar coordinates in rover space
    # Calculate distance to each pixel
    dist = np.sqrt(x_pixel**2 + y_pixel**2)
    # Calculate angle away from vertical for each pixel
    angles = np.arctan2(y_pixel, x_pixel)
    return dist, angles

# Define a function to map rover space pixels to world space
def rotate_pix(xpix, ypix, yaw):
    # Convert yaw to radians
    yaw_rad = yaw * np.pi / 180
    xpix_rotated = (xpix * np.cos(yaw_rad)) - (ypix * np.sin(yaw_rad))
                            
    ypix_rotated = (xpix * np.sin(yaw_rad)) + (ypix * np.cos(yaw_rad))
    # Return the result  
    return xpix_rotated, ypix_rotated

def translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale): 
    # Apply a scaling and a translation
    xpix_translated = (xpix_rot / scale) + xpos
    ypix_translated = (ypix_rot / scale) + ypos
    # Return the result  
    return xpix_translated, ypix_translated


# Define a function to apply rotation and translation (and clipping)
# Once you define the two functions above this function should work
def pix_to_world(xpix, ypix, xpos, ypos, yaw, world_size, scale):
    # Apply rotation
    xpix_rot, ypix_rot = rotate_pix(xpix, ypix, yaw)
    # Apply translation
    xpix_tran, ypix_tran = translate_pix(xpix_rot, ypix_rot, xpos, ypos, scale)
    # Perform rotation, translation and clipping all at once
    x_pix_world = np.clip(np.int_(xpix_tran), 0, world_size - 1)
    y_pix_world = np.clip(np.int_(ypix_tran), 0, world_size - 1)
    # Return the result
    return x_pix_world, y_pix_world

# Define a function to perform a perspective transform
def perspect_transform(img, src, dst):
           
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (img.shape[1], img.shape[0]))# keep same size as input image
    
    return warped


# Apply the above functions in succession and update the Rover state accordingly
def perception_step(Rover):
    # Perform perception steps to update Rover()
    # TODO: 
    # NOTE: camera image is coming to you in Rover.img
    # 1) Define source and destination points for perspective transform
    
    #Define calibration box in source (actual) and destination (desired) coordinates
    # These source and destination points are defined to warp the image
    # to a grid where each 10x10 pixel square represents 1 square meter
    # The destination box will be 2*dst_size on each side
    dst_size = 5 
    # Set a bottom offset to account for the fact that the bottom of the image 
    # is not the position of the rover but a bit in front of it
    # this is just a rough guess, feel free to change it!
    bottom_offset = 6
    source = np.float32([[14, 140], [301 ,140],[200, 96], [118, 96]])
    destination = np.float32([[Rover.img.shape[1]/2 - dst_size, Rover.img.shape[0] - bottom_offset],
                      [Rover.img.shape[1]/2 + dst_size, Rover.img.shape[0] - bottom_offset],
                      [Rover.img.shape[1]/2 + dst_size, Rover.img.shape[0] - 2*dst_size - bottom_offset], 
                      [Rover.img.shape[1]/2 - dst_size, Rover.img.shape[0] - 2*dst_size - bottom_offset],
                      ])
    
    # 2) Apply perspective transform
    warped = perspect_transform(Rover.img, source, destination)
    
    # 3) Apply color threshold to identify navigable terrain/obstacles/rock samples
    # color threshold to detect navigable terrain
    navigable_threshed= navigable_thresh(warped, rgb_thresh=(160, 160, 160))
    # color threshold to detect rock samples
    rock_threshed = rock_thresh(warped)
    # color threshold to detect obstacles
    obstacle_thresed= (navigable_threshed * -1)+1
    
    # 4) Update Rover.vision_image (this will be displayed on left side of screen)
    white_image = np.ones_like(Rover.img[:,:,0])
    white_warped = perspect_transform(white_image, source, destination)
       
    Rover.vision_image[:,:,0] = obstacle_thresed *255*white_warped
    Rover.vision_image[:,:,1] = rock_threshed *255*white_warped
    Rover.vision_image[:,:,2] = navigable_threshed *255*white_warped

    # 5) Convert map image pixel values to rover-centric coords
    
    # Calculate pixel values in rover-centric coords and distance/angle to all pixels for navigabled terrain
    xpix_navigable, ypix_navigable = rover_coords(navigable_threshed)
    dist_navigable, angles_navigable = to_polar_coords(xpix_navigable, ypix_navigable)
    mean_dir_navigable = np.mean(angles_navigable)

    # Calculate pixel values in rover-centric coords and distance/angle to all pixels for rock samples
    xpix_rock, ypix_rock = rover_coords(rock_threshed)
    dist_rock, angles_rock = to_polar_coords(xpix_rock, ypix_rock )
    mean_dir_rock = np.mean(angles_rock)

    # Calculate pixel values in rover-centric coords and distance/angle to all pixels for obstacles
    xpix_obstacle, ypix_obstacle = rover_coords(obstacle_thresed)
    dist_obstacle, angles_obstacle = to_polar_coords(xpix_obstacle, ypix_obstacle)
    mean_dir_obstacle = np.mean(angles_obstacle)
    
    
    
    # 6) Convert rover-centric pixel values to world coordinates
    scale = 10
    # Get navigable pixel positions in world coords
    x_world, y_world = pix_to_world(xpix_navigable, ypix_navigable, Rover.pos[0], 
                                    Rover.pos[1], Rover.yaw, 
                                    Rover.worldmap.shape[0], scale)
    
    # Get navigable pixel positions in world coords
    rock_x_world, rock_y_world = pix_to_world(xpix_rock, ypix_rock, Rover.pos[0], 
                                    Rover.pos[1], Rover.yaw, 
                                    Rover.worldmap.shape[0], scale) 
    
    # Get navigable pixel positions in world coords
    obstacle_x_world, obstacle_y_world = pix_to_world(xpix_obstacle, ypix_obstacle, Rover.pos[0], 
                                    Rover.pos[1], Rover.yaw, 
                                    Rover.worldmap.shape[0], scale) 
    
    
    # 7) Update Rover worldmap (to be displayed on right side of screen)
    Rover.worldmap[obstacle_y_world, obstacle_x_world, 0] += 1
    Rover.worldmap[rock_y_world, rock_x_world, 1] += 1
    Rover.worldmap[y_world, x_world, 2] += 1


    # 8) Convert rover-centric pixel positions to polar coordinates
    # Update Rover pixel distances and angles
    Rover.nav_dists = dist_navigable
    Rover.nav_angles = angles_navigable
    
 
    
    
    return Rover