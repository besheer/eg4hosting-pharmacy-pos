"""Code-native crescent and Bowl of Hygieia mark, without external assets."""
LOGO_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="هلال وكأس وثعبان"><path d="M42 9C2 14 1 79 42 91C15 71 15 29 42 9Z" fill="#76e0ca"/><path d="M37 52H87C83 70 75 74 62 74S42 68 37 52Z" fill="#e7fbf5"/><path d="M62 74V88M49 90H76" stroke="#e7fbf5" stroke-width="6" stroke-linecap="round"/><path d="M61 18C83 13 88 34 70 39C48 45 48 52 65 58C82 65 76 75 60 80" fill="none" stroke="#36c7a2" stroke-width="7" stroke-linecap="round"/><ellipse cx="59" cy="18" rx="9" ry="6" fill="#36c7a2"/><circle cx="56" cy="16" r="1.5" fill="#112b3c"/></svg>'''


def draw_splash_mark(parent):
    import tkinter as tk
    bg='#112b3c'
    c=tk.Canvas(parent,width=82,height=82,bg=bg,highlightthickness=0)
    # Same crescent + cup and winding snake, scaled to splash dimensions.
    c.create_oval(3,7,55,77,fill='#76e0ca',outline='')
    c.create_oval(19,2,65,79,fill=bg,outline='')
    c.create_polygon(30,43,71,43,67,53,60,59,50,61,40,56,fill='#e7fbf5',outline='')
    c.create_line(50,60,50,72,fill='#e7fbf5',width=5)
    c.create_line(40,74,62,74,fill='#e7fbf5',width=5,capstyle='round')
    c.create_line(49,16,68,14,73,27,57,33,39,40,45,46,61,53,61,61,49,66,smooth=True,fill='#36c7a2',width=5,capstyle='round')
    c.create_oval(42,11,56,21,fill='#36c7a2',outline='')
    c.create_oval(45,13,48,16,fill=bg,outline='')
    return c
