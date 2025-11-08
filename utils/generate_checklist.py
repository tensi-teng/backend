
def generate_checklist(equipment_list):
    equipment_list = [e.lower().strip() for e in (equipment_list or [])]
    checklist = []
    if 'dumbbell' in equipment_list:
        checklist += ['10 Dumbbell Squats', '10 Dumbbell Lunges', '10 Dumbbell Shoulder Press']
    if 'mat' in equipment_list:
        checklist += ['15 Push-Ups', '20 Crunches', '30s Plank']
    if 'resistance band' in equipment_list or 'band' in equipment_list:
        checklist += ['15 Band Rows', '15 Band Bicep Curls']
    if 'kettlebell' in equipment_list:
        checklist += ['12 Kettlebell Swings', '10 Goblet Squats']
    if not checklist:
        checklist = ['20 Jumping Jacks', '15 Bodyweight Squats']
    return [{'task': t, 'done': False} for t in checklist]
