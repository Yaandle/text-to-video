import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Line3DCollection

# Define pyramid vertices
def create_prism():
    """Create vertices for a pyramid"""
    # Apex point (top)
    apex = np.array([[0, 0, 0.8]])  # vertex 0
    
    # Base triangle (bottom)
    base = np.array([
        [0, 0.866, -0.5],      # vertex 1
        [-0.75, -0.433, -0.5], # vertex 2
        [0.75, -0.433, -0.5]   # vertex 3
    ])
    
    return np.vstack([apex, base])

# Define edges connecting vertices
edges = [
    [1, 2], [2, 3], [3, 1],  # base triangle
    [0, 1], [0, 2], [0, 3]   # edges from apex to base
]

# Rotation matrices
def rotation_matrix_x(theta):
    return np.array([
        [1, 0, 0],
        [0, np.cos(theta), -np.sin(theta)],
        [0, np.sin(theta), np.cos(theta)]
    ])

def rotation_matrix_y(theta):
    return np.array([
        [np.cos(theta), 0, np.sin(theta)],
        [0, 1, 0],
        [-np.sin(theta), 0, np.cos(theta)]
    ])

def rotation_matrix_z(theta):
    return np.array([
        [np.cos(theta), -np.sin(theta), 0],
        [np.sin(theta), np.cos(theta), 0],
        [0, 0, 1]
    ])

# Create figure
fig = plt.figure(figsize=(8, 8), facecolor='white')
ax = fig.add_subplot(111, projection='3d')

# Initial vertices
vertices = create_prism()

def init():
    """Initialize the animation"""
    ax.set_xlim([-1.5, 1.5])
    ax.set_ylim([-1.5, 1.5])
    ax.set_zlim([-1.5, 1.5])
    ax.set_facecolor('white')
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('none')
    ax.yaxis.pane.set_edgecolor('none')
    ax.zaxis.pane.set_edgecolor('none')
    return []

def update(frame):
    """Update function for animation"""
    ax.clear()
    
    # Set up the axis again
    ax.set_xlim([-1.5, 1.5])
    ax.set_ylim([-1.5, 1.5])
    ax.set_zlim([-1.5, 1.5])
    ax.set_facecolor('white')
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_zticks([])
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor('none')
    ax.yaxis.pane.set_edgecolor('none')
    ax.zaxis.pane.set_edgecolor('none')
    
    # Rotation angles - all equivalent speeds
    angle_y = frame * 0.015
    angle_x = frame * 0.015
    angle_z = frame * 0.015
    
    # Hovering effect (gentle up and down)
    hover_offset = 0.15 * np.sin(frame * 0.015)
    
    # Apply rotations
    rot_y = rotation_matrix_y(angle_y)
    rot_x = rotation_matrix_x(angle_x)
    combined_rotation = rot_y @ rot_x
    
    # Rotate vertices
    rotated_vertices = vertices @ combined_rotation.T
    
    # Apply hover offset
    rotated_vertices[:, 2] += hover_offset
    
    # Draw edges
    for edge in edges:
        points = rotated_vertices[edge]
        ax.plot3D(points[:, 0], points[:, 1], points[:, 2], 
                 color='black', linewidth=2, solid_capstyle='round')
    
    return []

# Create animation
anim = FuncAnimation(fig, update, init_func=init, frames=500, 
                    interval=30, blit=True, repeat=True)

plt.tight_layout()
plt.show()