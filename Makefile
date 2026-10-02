# El python del sistema, no el de mise: es el que trae gi (GTK), y con él
# corren también las pruebas de la isla. Sin gi, esas se saltan.
PYTHON ?= /usr/bin/python3

.PHONY: test
test:
	$(PYTHON) -m unittest discover -s tests
