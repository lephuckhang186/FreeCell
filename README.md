# FreeCell (pygame)

Ban game FreeCell viet bang Python + pygame, tach module ro rang de de bao tri va mo rong.

## Cai dat

```bash
python -m pip install -r requirements.txt
```

## Chay game

```bash
python main.py
```

## Dieu khien

- Keo tha chuot trai de di chuyen la bai
- Double-click de auto-move len foundation
- Click nhanh 1 la (khong keo) de thu auto-move
- `Z` undo, `Y` redo
- `R` de chia van moi
- `ESC` de thoat

## Cau truc

- `main.py`: diem vao chuong trinh
- `freecell/constants.py`: thong so UI/game
- `freecell/models.py`: model la bai
- `freecell/state.py`: tao trang thai, chia bai
- `freecell/rules.py`: luat di chuyen
- `freecell/layout.py`: toa do board va hit-test
- `freecell/ui.py`: ve giao dien
- `freecell/game.py`: game loop va input

